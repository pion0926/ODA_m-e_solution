"""Read-only performance preview and an immutable, user-reviewed analysis scope."""
import hashlib
import json

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from .db import connection
from .document_classification import pdm_slots
from .foundation import state as foundation_state
from .project_lifecycle import capture_input_snapshot, document_blocks_workflow
from .pdm_mapping_policy import decision, manual_overrides, VERSION


def build_plan(conn=None):
    if conn is None:
        with connection() as current:
            return build_plan(current)
    from .pdm_monitoring import _model_from_slots, _matches_pdm_requirement
    rows = conn.execute('SELECT * FROM evaluation_intake_documents ORDER BY queue_position').fetchall()
    foundations = foundation_state(conn)
    source = next((row for row in reversed(rows) if row['upload_role'] == 'pdm' and row['status'] == 'completed'), None)
    model = _model_from_slots(pdm_slots(source.get('analysis'))) if source else {'tiers': []}
    from .performance_delta import history, fingerprint
    previous=conn.execute('SELECT id,source_document_id,model FROM pdm_models ORDER BY created_at DESC LIMIT 1').fetchone()
    records=history(previous,rows,[i for tier in model['tiers'] for i in tier['indicators']],source['id'] if source else None)
    indicators = []
    for tier in model['tiers']:
        for indicator in tier['indicators']:
            selected = []
            for doc in rows:
                if doc['status'] != 'completed':
                    continue
                analysis = doc.get('analysis') or {}
                matched = decision(doc, indicator['id'], source['id'])
                if matched:
                    selected.append(str(doc['id']))
            analyzed=[str(doc['id']) for doc in rows if fingerprint(source['id'],doc,indicator) in records]
            indicators.append({**indicator, 'tier': tier['id'], 'tier_name': tier['name'],
                'mapping_details': {str(doc['id']): decision(doc,indicator['id'],source['id']) for doc in rows if str(doc['id']) in selected},
                'document_ids':[id for id in selected if id not in analyzed],
                'retained_document_ids':[id for id in selected if id in analyzed], 'analyzed_document_ids':analyzed})
    documents = [{'id': str(row['id']), 'file_name': row['original_name'], 'status': row['status'],
                  'document_profiles': ((row.get('analysis') or {}).get('evidence_matches') or {}).get('document_profiles', []),
                  'progress': row['progress'], 'upload_role': row['upload_role'], 'error_message': row.get('error_message')}
                 for row in rows]
    snapshot = capture_input_snapshot(conn)
    active = conn.execute("""SELECT id FROM pdm_refresh_runs WHERE status IN ('queued','running')
                             UNION ALL SELECT id FROM evaluation_runs WHERE status IN ('queued','running') LIMIT 1""").fetchone()
    pending = sum(document_blocks_workflow(row) for row in rows)
    ready = bool(foundations['ready'] and indicators and not pending and not active)
    message = ('사업계획서와 PDM을 먼저 등록하고 분석을 완료해 주세요.' if not foundations['ready']
               else '다른 성과 분석 또는 DAC 평가가 진행 중입니다.' if active
               else f'문서 {pending}건의 기본 분석·매칭이 완료되어야 실행할 수 있습니다.' if pending
               else '지표별 분석 문서를 확인하고 필요한 자료를 추가한 뒤 분석을 실행해 주세요.')
    old_pairs=(previous or {}).get('model',{}).get('monitoring',{}).get('pair_results',{})
    recheck_count=sum(key not in records for key in old_pairs)
    if ready and recheck_count:
        message += f' 이전에 측정값 없이 저장되어 검토 근거가 없는 {recheck_count}개 조합은 다시 확인합니다.'
    legacy_count = sum(row['status']=='completed' and row.get('upload_role')=='evidence'
                       and ((row.get('analysis') or {}).get('evidence_matches') or {}).get('version') != VERSION for row in rows)
    if legacy_count:
        message += f' 기존 자료 {legacy_count}건은 증빙 목적 재검토 전입니다. 과거 주제 기반 연결은 자동 선택하지 않으며 필요한 문서는 직접 추가할 수 있습니다.'
    payload = {'source_document_id': str(source['id']) if source else None,
               'baseline_model_id':str(previous['id']) if previous else None,
               'source_file_name': source['original_name'] if source else None,
               'input_snapshot': snapshot, 'indicators': indicators, 'documents': documents}
    revision = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    return {**payload, 'revision': revision, 'ready': ready, 'message': message, 'pending_count': pending}


def validate_selection(current, revision, selections):
    if not current['ready']:
        raise HTTPException(409, current['message'])
    if current['revision'] != revision:
        raise HTTPException(409, '자료 또는 매핑이 변경되었습니다. 분석 개요를 새로고침하고 다시 확인해 주세요.')
    expected = {item['id'] for item in current['indicators']}
    if set(selections) != expected:
        raise HTTPException(422, '현재 PDM의 모든 지표에 대한 문서 매핑을 확인해 주세요.')
    allowed = {doc['id'] for doc in current['documents'] if doc['status'] == 'completed'}
    mappings = {}
    new_mappings={}
    for indicator, ids in selections.items():
        if len(ids) != len(set(ids)) or not set(ids) <= allowed:
            raise HTTPException(422, '분석이 완료된 현재 프로젝트 문서만 중복 없이 연결할 수 있습니다.')
        item=next(i for i in current['indicators'] if i['id']==indicator)
        if set(ids)&set(item.get('analyzed_document_ids',[])):
            raise HTTPException(409,'이미 분석한 문서–지표 조합입니다. 분석 대상을 새로 확인해 주세요.')
        new_mappings[indicator]=sorted(ids)
        mappings[indicator] = sorted(set(ids)|set(item.get('retained_document_ids',[])))
    if not any(new_mappings.values()):
        raise HTTPException(409,'신규 문서 또는 신규 매핑이 없습니다. 기존 분석 결과를 유지합니다.')
    return {'revision': revision, 'source_document_id': current['source_document_id'],
            'source_file_name': current['source_file_name'], 'input_snapshot': current['input_snapshot'],
            'indicators': current['indicators'], 'mappings': mappings, 'new_mappings':new_mappings,
            'baseline_model_id':current.get('baseline_model_id')}


def save_overrides(conn, current, reviewed):
    """Persist explicit inclusions and exclusions without changing document-content revision."""
    for doc in current['documents']:
        if doc['status'] != 'completed':
            continue
        row = conn.execute('SELECT analysis FROM intake_documents WHERE id=%s', (doc['id'],)).fetchone()
        included, excluded = manual_overrides((row or {}).get('analysis') or {}, reviewed['source_document_id'])
        for item in current['indicators']:
            before = doc['id'] in [*item.get('document_ids',[]), *item.get('retained_document_ids',[])]
            after = doc['id'] in reviewed['mappings'][item['id']]
            if after and not before:
                included.add(item['id']); excluded.discard(item['id'])
            elif before and not after:
                excluded.add(item['id']); included.discard(item['id'])
        conn.execute("""UPDATE intake_documents SET analysis=jsonb_set(COALESCE(analysis,'{}'::jsonb),
            '{pdm_mapping_overrides}',%s) WHERE id=%s""",
            (Jsonb({'version':VERSION,'source_document_id': reviewed['source_document_id'], 'included': sorted(included), 'excluded': sorted(excluded)}), doc['id']))
