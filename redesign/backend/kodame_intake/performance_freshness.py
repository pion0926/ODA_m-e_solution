"""Performance input receipts exclude their own outputs and unrelated DAC/report work."""
from functools import lru_cache
from pathlib import Path

from .db import connection, current_project_id
from .document_classification import pdm_slots
from .evaluation_versions import digest
from .llm_models import current_llm_model
from .project_lifecycle import input_snapshot_from_rows

VERSION = 'performance-input-v1'


@lru_cache(maxsize=1)
def policy_fingerprints():
    """Immutable deployment source bytes, with extraction and reconciliation separate."""
    root = Path(__file__).parent
    def fingerprint(names):
        return digest({name: (root / name).read_bytes().hex() for name in names})
    from .performance_risk_policy import RISK_SYSTEM_PROMPT
    return {
        'extraction': fingerprint(('pdm_evidence.py', 'measurement_semantics.py',
            'measurement_dimensions.py', 'ai/prompts/performance_measurements.md')),
        'reconciliation': fingerprint(('performance_delta.py', 'performance_scope.py',
            'performance_targets.py', 'performance_status.py', 'pdm_targets.py',
            'pdm_mapping_policy.py', 'pdm_monitoring.py')),
        'risk': digest({'prompt': RISK_SYSTEM_PROMPT, 'implementation':
                       (root / 'performance_risk_policy.py').read_bytes().hex()}),
    }


def inputs_from_documents(documents, *, model=None, project_id=None, policies=None):
    source = next((row for row in sorted(documents, key=lambda row: int(row.get('queue_position') or 0), reverse=True)
                   if row.get('upload_role') == 'pdm' and row.get('status') == 'completed'), None)
    purposes = []
    for row in documents:
        analysis = row.get('analysis') or {}
        matched = analysis.get('evidence_matches') or {}
        purposes.append({'id': str(row['id']), 'upload_role': row.get('upload_role'),
            'pdm_matches': {key: matched.get(key) for key in ('version', 'pdm')},
            'pdm_match_source': (matched.get('sources') or {}).get('pdm'),
            'manual': analysis.get('pdm_mapping_overrides'),
            'facts': [fact for fact in (analysis.get('registration_facts') or {}).get('facts', [])
                      if fact.get('pdm_indicator_ids')]})
    return {'version': VERSION, 'project_id': str(project_id or current_project_id()),
        'document_digest': input_snapshot_from_rows(documents)['document_digest'],
        'source_document_id': str(source['id']) if source else None,
        'source_digest': digest(pdm_slots({**(source.get('analysis') or {}), 'upload_role': source['upload_role']})) if source else None,
        'mapping_digest': digest(sorted(purposes, key=lambda row: row['id'])),
        'model': model or current_llm_model(), 'policies': policies or policy_fingerprints()}


def capture_inputs(conn=None):
    if conn is None:
        with connection() as current:
            return capture_inputs(current)
    # Never load source files, measurement caches or DAC full-text caches on this read path.
    rows = conn.execute("""SELECT id,sha256,status,updated_at,upload_role,queue_position,
        jsonb_build_object('upload_role',analysis->'upload_role',
          'content_classification',analysis->'content_classification',
          'pdm_mapping_overrides',analysis->'pdm_mapping_overrides',
          'evidence_matches',jsonb_build_object('version',analysis->'evidence_matches'->'version',
            'pdm',analysis->'evidence_matches'->'pdm',
            'sources',jsonb_build_object('pdm',analysis->'evidence_matches'->'sources'->'pdm')),
          'registration_facts',analysis->'registration_facts') AS analysis
        FROM evaluation_intake_documents ORDER BY queue_position""").fetchall()
    return inputs_from_documents(rows)


def matches(saved, current):
    required = ('version', 'project_id', 'document_digest', 'source_document_id',
                'source_digest', 'mapping_digest', 'model', 'policies')
    return (isinstance(saved, dict) and isinstance(current, dict)
            and saved.get('version') == current.get('version') == VERSION
            and all(saved.get(key) and saved.get(key) == current.get(key) for key in required))


def analysis_status(model, current):
    monitoring = model.get('monitoring') or {}
    saved = monitoring.get('performance_inputs')
    incomplete = ((monitoring.get('evidence_analysis') or {}).get('incomplete_indicator_count')
                  or any(item.get('measurement_status') == 'incomplete' or item.get('mapping_review_required')
                         for item in model.get('performance_indicators', [])))
    if matches(saved, current) and not incomplete:
        return 'current'
    return 'stale' if saved or monitoring.get('input_snapshot') else 'not_run'


def compatible_records(previous, records, current):
    """Keep proven measurements, but never label another model's work as current.

    Ordinary history has already validated supported legacy extraction versions,
    count scopes, dimensions, source hashes, definitions and per-indicator reviews.
    Do not invalidate those proven records just to add the new input receipt.
    """
    from .pdm_evidence import MEASUREMENT_VERSION
    saved = ((previous or {}).get('model', {}).get('monitoring') or {}).get('performance_inputs')
    if saved and (saved.get('policies') or {}).get('extraction') != current['policies']['extraction']:
        return {}
    supported = {MEASUREMENT_VERSION, 'pdm-evidence-v7-proposals', 'pdm-evidence-v6-roles', 'pdm-evidence-v4-recheck'}
    return {key: record for key, record in records.items()
            if record.get('model') == current['model'] and record.get('measurement_version') in supported}


def extraction_changed(previous, current):
    saved = ((previous or {}).get('model', {}).get('monitoring') or {}).get('performance_inputs')
    return bool(saved and (saved.get('policies') or {}).get('extraction') != current['policies']['extraction'])


def execution_plan(plan, previous, documents, current):
    """Rebind only a queued model change; never expand the user's reviewed scope."""
    from copy import deepcopy
    reviewed = plan.get('performance_inputs') or {}
    if not matches({**reviewed, 'model': current['model']}, current):
        raise RuntimeError('분석 개요 확인 이후 문서·지표·매핑 또는 검토 규칙이 변경되었습니다. 최신 분석 개요를 다시 확인해 주세요.')
    if reviewed.get('model') == current['model']:
        return plan
    from .performance_delta import history, fingerprint
    result = deepcopy(plan)
    indicators = plan['indicators']
    records = compatible_records(previous, history(previous, documents, indicators, plan['source_document_id']), current)
    by_id = {str(doc['id']): doc for doc in documents}
    for indicator in indicators:
        key = indicator['id']
        reusable = {ident for ident in plan['mappings'][key] if ident in by_id
                    and fingerprint(plan['source_document_id'], by_id[ident], indicator) in records}
        result['new_mappings'][key] = sorted(set(plan['mappings'][key]) - reusable)
        result.setdefault('restored_mappings', {})[key] = sorted(set(plan.get('restored_mappings', {}).get(key, [])) & reusable)
    result['performance_inputs'] = current
    result['reconciliation_indicator_ids'] = sorted({item['id'] for item in indicators})
    result['execution_model_change'] = {'reviewed_model': reviewed.get('model'),
        'executed_model': current['model'], 'new_pair_count': sum(map(len, result['new_mappings'].values())),
        'reason': '대기 중 변경한 연동 모델로 확인한 문서·지표 범위만 분석합니다.'}
    return result
