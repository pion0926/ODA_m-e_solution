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


def deferred_legacy_pairs(documents, indicators, source_id, previous):
    """Retain proven v3 history during v4 rollout, without proposing old matches."""
    if not previous or str(previous.get('source_document_id')) != str(source_id):
        return {}
    from .performance_delta import fingerprint
    model = previous.get('model') or {}
    monitoring = model.get('monitoring') or {}
    reviewed = monitoring.get('reviewed_mappings') or {}
    deferred = monitoring.get('deferred_mappings') or {}
    old = {item['id']:item for item in model.get('performance_indicators', [])}
    records = monitoring.get('pair_results') or {}
    result = {}
    for indicator in indicators:
        prior = old.get(indicator['id'])
        if (not prior or prior.get('indicator') != indicator.get('text',indicator.get('indicator'))
                or prior.get('evidence') != indicator.get('mov',indicator.get('evidence'))):
            continue
        prior_ids = set(reviewed.get(indicator['id'], prior.get('evidence_document_ids', []))) | set(deferred.get(indicator['id'], []))
        for document in documents:
            document_id = str(document['id'])
            analysis = document.get('analysis') or {}
            saved = analysis.get('evidence_matches') or {}
            if (document.get('status') != 'completed' or document_id not in prior_ids
                    or saved.get('version') != 3 or VERSION <= 3
                    or str(((saved.get('sources') or {}).get('pdm') or {}).get('id')) != str(source_id)
                    or decision(document, indicator['id'], source_id)):
                continue
            _, excluded = manual_overrides(analysis, source_id)
            if indicator['id'] in excluded:
                continue
            record = records.get(fingerprint(source_id, document, indicator)) or {}
            observed = any(str(item.get('document_id')) == document_id for item in prior.get('measurement_sources', []))
            if not (record.get('observations') or record.get('reviews') or observed):
                continue
            result.setdefault(indicator['id'], []).append(document_id)
    return {key:sorted(values) for key,values in result.items()}


def selected_recheck_count(source_id, documents, indicators, old_pairs, reusable_pairs):
    from .performance_delta import fingerprint
    selected = {fingerprint(source_id, document, item) for item in indicators for document in documents
                if str(document['id']) in item['document_ids'] + item['retained_document_ids']}
    return sum(key in old_pairs and key not in reusable_pairs for key in selected)


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
    from .performance_targets import reference_targets, reference_signature, target_policy_needs_review
    prior_indicators = {item['id']:item for item in (previous or {}).get('model', {}).get('performance_indicators', [])
                        if source and str((previous or {}).get('source_document_id')) == str(source['id'])}
    deferred = deferred_legacy_pairs(rows, [item for tier in model['tiers'] for item in tier['indicators']],
                                     source['id'] if source else None, previous)
    text_cache = {}
    target_changes = []
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
            prior = prior_indicators.get(indicator['id'], {})
            references = reference_targets(rows, indicator, prior, text_cache, source_id=source['id'])
            previous_references = prior.get('target_reference_sources', prior.get('measurement_sources', []))
            if (reference_signature(references) != reference_signature(previous_references)
                    or target_policy_needs_review(prior)):
                target_changes.append(indicator['id'])
            indicators.append({**indicator, 'tier': tier['id'], 'tier_name': tier['name'],
                'mapping_details': {str(doc['id']): decision(doc,indicator['id'],source['id']) for doc in rows if str(doc['id']) in selected},
                'document_ids':[id for id in selected if id not in analyzed],
                'deferred_document_ids':deferred.get(indicator['id'], []),
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
    recheck_count=selected_recheck_count(source['id'] if source else None, rows, indicators, old_pairs, records)
    if ready and recheck_count:
        message += f' 이전 검토 근거 또는 집계 범위를 보완할 {recheck_count}개 조합은 다시 확인합니다.'
    legacy_count = sum(row['status']=='completed' and row.get('upload_role')=='evidence'
                       and ((row.get('analysis') or {}).get('evidence_matches') or {}).get('version') != VERSION for row in rows)
    if legacy_count:
        message += f' 기존 자료 {legacy_count}건은 증빙 목적 재검토 전입니다. 과거 주제 기반 연결은 자동 선택하지 않으며 필요한 문서는 직접 추가할 수 있습니다.'
    if deferred:
        message += f' 이미 검토한 {sum(map(len,deferred.values()))}개 이전 조합은 목적 재검토 전까지 참고 결과로 보존합니다. 신규 문서는 별도로 분석할 수 있습니다.'
    prior_model = (previous or {}).get('model', {})
    old_mappings = prior_model.get('monitoring', {}).get('reviewed_mappings', {})
    if not old_mappings:
        old_mappings = {item['id']: item.get('evidence_document_ids', [])
                        for item in prior_model.get('performance_indicators', [])}
    prior_deferred = prior_model.get('monitoring', {}).get('deferred_mappings', {})
    mapping_changes = [item['id'] for item in indicators if (set(old_mappings.get(item['id'], [])) |
                       set(prior_deferred.get(item['id'], []))) - set(deferred.get(item['id'], [])) !=
                       set(item['document_ids'] + item['retained_document_ids'])]
    if ready and mapping_changes and not any(item['document_ids'] for item in indicators):
        message += ' 증빙 연결이 변경된 지표는 기존 원문을 다시 호출하지 않고 유효한 근거로 결과를 재정리합니다.'
    payload = {'source_document_id': str(source['id']) if source else None,
               'baseline_model_id':str(previous['id']) if previous else None,
               'source_file_name': source['original_name'] if source else None,
               'input_snapshot': snapshot, 'indicators': indicators, 'documents': documents,
               'deferred_mappings':deferred, 'recheck_count':recheck_count,
               'mapping_changed_indicator_ids': sorted(set(mapping_changes) | set(target_changes))}
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
    if not any(new_mappings.values()) and not current.get('mapping_changed_indicator_ids'):
        raise HTTPException(409,'신규 문서 또는 신규 매핑이 없습니다. 기존 분석 결과를 유지합니다.')
    return {'revision': revision, 'source_document_id': current['source_document_id'],
            'source_file_name': current['source_file_name'], 'input_snapshot': current['input_snapshot'],
            'indicators': current['indicators'], 'mappings': mappings, 'new_mappings':new_mappings,
            'mapping_changed_indicator_ids': current.get('mapping_changed_indicator_ids', []),
            'deferred_mappings':current.get('deferred_mappings', {}),
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
