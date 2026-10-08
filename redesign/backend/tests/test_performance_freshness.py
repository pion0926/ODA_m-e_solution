"""A PDM save is an output, not a change to the evidence it just reviewed."""
import copy
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from kodame_intake import performance_freshness as freshness
from kodame_intake.dac_pdm import refresh_context
from kodame_intake.performance_review import validate_selection
from kodame_intake.pdm_evidence import MEASUREMENT_VERSION


POLICIES = {'extraction': 'extract-1', 'reconciliation': 'reconcile-1', 'risk': 'risk-1'}


def documents():
    return [{'id': 'pdm', 'sha256': 'source-hash', 'status': 'completed', 'upload_role': 'pdm',
        'updated_at': '2026-01-01T00:00:00+00:00', 'queue_position': 1,
        'analysis': {'content_classification': {'version': 'content-roles-v1', 'is_pdm_source': True,
                    'slots': {'outputs_indicator': '1. 교원 양성 인원 (명)', 'outputs_mov': '1. 수료 명단'}}}},
        {'id': 'evidence', 'sha256': 'evidence-hash', 'status': 'completed', 'upload_role': 'evidence',
         'updated_at': '2026-01-02T00:00:00+00:00', 'queue_position': 2,
         'analysis': {'pdm_mapping_overrides': {'version': 4, 'source_document_id': 'pdm',
                       'included': ['outputs-1'], 'excluded': []},
                      'registration_facts': {'facts': [{'kind': 'actual', 'pdm_indicator_ids': ['outputs-1'], 'value': '4명'}]}}}]


def contract(rows=None, **kwargs):
    return freshness.inputs_from_documents(rows or documents(), model='model-a', project_id='project-a',
                                           policies=POLICIES, **kwargs)


def test_pdm_own_output_dac_report_and_cache_writes_do_not_invalidate_inputs():
    before = contract()
    rows = documents()
    rows[1]['analysis'].update(pdm_measurements={'observations': ['new output']},
        pdm_measurement_cache={'digest': 'new'}, dac_fulltext={'body': 'large'}, report={'generated': True})
    assert contract(rows) == before
    model = {'monitoring': {'input_snapshot': {'workflow_digest': 'old PDM output'}, 'performance_inputs': before},
             'performance_indicators': [{'actual': '4명'}]}
    assert freshness.analysis_status(model, contract(rows)) == 'current'
    # A later overview/DAC/report version changes the global workflow fingerprint,
    # but neither overwrites the dedicated input receipt nor its saved measurements.
    model['monitoring']['input_snapshot']['workflow_digest'] = 'new DAC/report output'
    assert freshness.analysis_status(model, contract(rows)) == 'current'
    assert model['performance_indicators'][0]['actual'] == '4명'


@pytest.mark.parametrize('change', ['upload', 'replace', 'exclude', 'reanalysis', 'pdm', 'manual', 'facts', 'model', 'policy', 'project'])
def test_real_inputs_remain_stale(change):
    before = contract(); rows = documents()
    if change == 'upload': rows.append({**rows[1], 'id': 'new', 'sha256': 'new'})
    elif change == 'replace': rows[1]['sha256'] = 'replacement'
    elif change == 'exclude': rows.pop()
    elif change == 'reanalysis': rows[1]['updated_at'] = '2026-02-01T00:00:00+00:00'
    elif change == 'pdm': rows[0]['analysis']['content_classification']['slots']['outputs_indicator'] = '1. 졸업 인원 (명)'
    elif change == 'manual': rows[1]['analysis']['pdm_mapping_overrides']['excluded'] = ['outputs-1']
    elif change == 'facts': rows[1]['analysis']['registration_facts']['facts'][0]['value'] = '5명'
    current = contract(rows)
    if change == 'model': current['model'] = 'model-b'
    elif change == 'policy': current['policies'] = {**POLICIES, 'reconciliation': 'new'}
    elif change == 'project': current['project_id'] = 'other-project'
    assert not freshness.matches(before, current)
    assert freshness.analysis_status({'monitoring': {'performance_inputs': before}}, current) == 'stale'


def test_missing_legacy_and_partial_receipts_never_silently_become_current():
    for model in ({}, {'monitoring': {'input_snapshot': {'document_digest': contract()['document_digest']}}},
                  {'monitoring': {'performance_inputs': contract(), 'evidence_analysis': {'incomplete_indicator_count': 1}}}):
        assert freshness.analysis_status(model, contract()) != 'current'
    saved = contract(); saved.pop('source_digest')
    assert not freshness.matches(saved, contract())


def test_model_and_extraction_compatibility_precede_cached_receipt_renewal():
    records = {'ok': {'model': 'model-a', 'measurement_version': MEASUREMENT_VERSION},
               'different-model': {'model': 'model-b', 'measurement_version': MEASUREMENT_VERSION},
               'unknown': {'measurement_version': MEASUREMENT_VERSION},
               'old-policy': {'model': 'model-a', 'measurement_version': 'legacy'}}
    assert set(freshness.compatible_records(None, records, contract())) == {'ok'}
    previous = {'model': {'monitoring': {'performance_inputs': contract()}}}
    current = contract(); current['policies'] = {**POLICIES, 'extraction': 'new'}
    assert freshness.compatible_records(previous, records, current) == {}
    current['policies'] = {**POLICIES, 'reconciliation': 'new'}
    assert set(freshness.compatible_records(previous, records, current)) == {'ok'}


def test_supported_legacy_pairs_survive_receipt_migration_after_existing_history_checks():
    from kodame_intake.performance_delta import history
    rows = documents()
    records = {version: {'document_id': 'evidence', 'indicator_id': 'outputs-1', 'model': 'model-a',
                         'measurement_version': version, 'observations': [], 'reviews': [{'status': 'no_measurement'}]}
               for version in ('pdm-evidence-v4-recheck', 'pdm-evidence-v6-roles', 'pdm-evidence-v7-proposals', MEASUREMENT_VERSION)}
    previous = {'source_document_id': 'pdm', 'model': {'monitoring': {'pair_results': records}}}
    non_count = [{'id': 'outputs-1', 'indicator': '수료 비율 (%)', 'evidence': '명단'}]
    valid = history(previous, rows, non_count, 'pdm')
    assert freshness.compatible_records(previous, valid, contract()) == records
    # Introducing count-scope validation still rejects legacy empty reviews;
    # the new receipt filter must never revive a pair history already rejected.
    count = [{'id': 'outputs-1', 'indicator': '완료 행사 횟수 (회)', 'evidence': '결과보고'}]
    valid_count = history(previous, rows, count, 'pdm')
    assert set(freshness.compatible_records(previous, valid_count, contract())) == {MEASUREMENT_VERSION}


def test_normal_review_can_renew_receipt_without_fabricating_new_pairs():
    plan = {'ready': True, 'revision': 'r', 'message': '', 'source_document_id': 'pdm', 'source_file_name': 'pdm',
            'baseline_model_id': 'previous', 'input_snapshot': {}, 'performance_inputs': contract(),
            'freshness_review_required': True, 'documents': [{'id': 'evidence', 'status': 'completed'}],
            'indicators': [{'id': 'i', 'retained_document_ids': ['evidence'], 'analyzed_document_ids': ['evidence']}],
            'mapping_changed_indicator_ids': []}
    reviewed = validate_selection(plan, 'r', {'i': []})
    assert reviewed['mappings'] == {'i': ['evidence']}
    assert reviewed['new_mappings'] == {'i': []}
    assert reviewed['freshness_review_required']
    plan['freshness_review_required'] = False
    with pytest.raises(HTTPException) as error:
        validate_selection(plan, 'r', {'i': []})
    assert error.value.status_code == 409


def test_dac_reader_accepts_only_dedicated_inputs_and_never_runs_analysis():
    row = {'id': 'snapshot-after-own-save', 'source_document_id': 'pdm', 'source_file_name': 'pdm',
           'created_at': datetime.now(timezone.utc), 'model': {'monitoring': {
               'input_snapshot': {'document_digest': 'same', 'workflow_digest': 'pre-save'},
               'performance_inputs': contract()}, 'performance_indicators': []}}
    conn = Mock(); conn.execute.return_value.fetchone.return_value = row
    conn.execute.return_value.fetchall.return_value = []
    with patch('kodame_intake.dac_pdm.connection') as connection, \
         patch('kodame_intake.dac_pdm.capture_inputs', return_value=contract()), \
         patch('kodame_intake.pdm_monitoring.refresh_pdm_model') as analysis:
        connection.return_value.__enter__.return_value = conn
        assert refresh_context([{'id': 'pdm', 'ref': 'D001'}])['performance_analysis_status'] == 'current'
        analysis.assert_not_called()


def test_projection_ignores_cache_bodies_and_matches_full_analysis_contract():
    conn = Mock(); conn.execute.return_value.fetchall.return_value = documents()
    with patch.object(freshness, 'current_llm_model', return_value='model-a'), \
         patch.object(freshness, 'current_project_id', return_value='project-a'), \
         patch.object(freshness, 'policy_fingerprints', return_value=POLICIES):
        assert freshness.capture_inputs(conn) == contract()
    sql = conn.execute.call_args.args[0]
    assert 'SELECT *' not in sql and 'pdm_measurement_cache' not in sql and 'dac_fulltext' not in sql


def test_queued_model_change_rebinds_only_reviewed_pairs():
    from kodame_intake.performance_delta import fingerprint
    rows = documents()
    indicator = {'id': 'outputs-1', 'text': '교원 양성 인원 (명)', 'mov': '수료 명단'}
    record = {'document_id': 'evidence', 'indicator_id': 'outputs-1', 'model': 'model-a',
              'measurement_version': MEASUREMENT_VERSION, 'observations': [],
              'reviews': [{'status': 'no_measurement'}]}
    previous = {'source_document_id': 'pdm', 'model': {'monitoring': {'performance_inputs': contract(),
        'pair_results': {fingerprint('pdm', rows[1], indicator): record}}}}
    plan = {'performance_inputs': contract(), 'source_document_id': 'pdm', 'indicators': [indicator],
            'mappings': {'outputs-1': ['evidence']}, 'new_mappings': {'outputs-1': []}}
    current = contract(); current['model'] = 'model-b'
    rebound = freshness.execution_plan(plan, previous, rows, current)
    assert rebound['mappings'] == plan['mappings']
    assert rebound['new_mappings'] == {'outputs-1': ['evidence']}
    assert rebound['execution_model_change']['executed_model'] == 'model-b'
    assert plan['new_mappings'] == {'outputs-1': []}
    assert rebound['performance_inputs']['model'] == 'model-b'
    for changed in ('document_digest', 'source_digest', 'mapping_digest', 'policies'):
        stale = copy.deepcopy(current); stale[changed] = 'different'
        with pytest.raises(RuntimeError, match='최신 분석 개요'):
            freshness.execution_plan(plan, previous, rows, stale)


@pytest.mark.parametrize('mapping_changes_during_run', [False, True])
def test_renewing_legacy_receipt_preserves_measurements_and_risks_without_ai(mapping_changes_during_run):
    from kodame_intake.pdm_monitoring import _refresh_pdm_model, _model_from_slots
    from kodame_intake.performance_delta import fingerprint
    from kodame_intake.performance_targets import TARGET_SELECTION_VERSION
    from kodame_intake.llm_models import current_llm_model
    rows = documents()
    for row in rows: row['original_name'] = row['id'] + '.pdf'
    slots = freshness.pdm_slots(rows[0]['analysis'])
    base = _model_from_slots(slots)
    item = next(item for tier in base['tiers'] for item in tier['indicators'])
    observation = {'indicator_id': item['id'], 'document_id': 'evidence', 'file_name': 'evidence.pdf',
                   'quote': '수료자 4명', 'kind': 'actual', 'value': '4명', 'period': '2026'}
    record = {'document_id': 'evidence', 'indicator_id': item['id'], 'model': current_llm_model(),
              'measurement_version': MEASUREMENT_VERSION, 'observations': [observation], 'reviews': []}
    previous = {'id': 'before', 'source_document_id': 'pdm', 'model': {**base,
        'performance_indicators': [{'id': item['id'], 'indicator': item['text'], 'evidence': item['mov'],
            'actual': '4명', 'target': '-', 'achievement_rate': None, 'measurement_status': 'extracted',
            'evidence_document_ids': ['evidence'], 'measurement_sources': [observation],
            'target_selection': {'version': TARGET_SELECTION_VERSION}, 'status': 'unset',
            'risk_analysis': {'analysis_source': 'ai', 'forecast': '기존 권고 보존'}}],
        'risk_analysis': {'status': 'completed', 'model': current_llm_model(), 'analyzed_count': 1},
        'monitoring': {'input_snapshot': {'document_digest': 'docs', 'workflow_digest': 'previous'},
            'reviewed_mappings': {item['id']: ['evidence']},
            'pair_results': {fingerprint('pdm', rows[1], item): record}}}}
    inputs = contract()
    final_inputs = {**inputs, 'mapping_digest': 'changed-during-run'} if mapping_changes_during_run else inputs
    snapshot = {'document_digest': 'docs', 'workflow_digest': 'before-self-save'}
    plan = {'revision': 'review', 'source_document_id': 'pdm', 'source_file_name': 'pdm.pdf',
        'baseline_model_id': 'before', 'performance_inputs': inputs, 'input_snapshot': snapshot,
        'indicators': [item], 'mappings': {item['id']: ['evidence']}, 'new_mappings': {item['id']: []},
        'freshness_review_required': True}
    conn = Mock(); conn.transaction.return_value.__enter__ = Mock(); conn.transaction.return_value.__exit__ = Mock(return_value=False)
    conn.execute.return_value.fetchone.return_value = previous
    with patch('kodame_intake.pdm_monitoring.connection') as connection, \
         patch('kodame_intake.pdm_monitoring._documents', return_value=rows), \
         patch('kodame_intake.pdm_monitoring._select_pdm_source', return_value=(rows[0], slots)), \
         patch('kodame_intake.project_lifecycle.capture_input_snapshot', return_value=snapshot), \
         patch.object(freshness, 'capture_inputs', side_effect=[inputs, final_inputs]), \
         patch('kodame_intake.pdm_evidence.extract_measurements') as extract, \
         patch('kodame_intake.pdm_monitoring.analyze_performance_risks') as risks, \
         patch('kodame_intake.pdm_jobs.finish_refresh') as finish:
        connection.return_value.__enter__.return_value = conn
        if mapping_changes_during_run:
            with pytest.raises(RuntimeError, match='기존 결과를 보존'):
                _refresh_pdm_model(analyze_risks=True, refresh_run_id='run', analysis_plan=plan)
        else:
            _refresh_pdm_model(analyze_risks=True, refresh_run_id='run', analysis_plan=plan)
    extract.assert_not_called(); risks.assert_not_called()
    if mapping_changes_during_run:
        finish.assert_not_called()
        assert not any('INSERT INTO pdm_models' in str(call.args[0]) for call in conn.execute.call_args_list)
        return
    saved = finish.call_args.args[3]
    assert saved['performance_indicators'][0]['actual'] == '4명'
    assert saved['performance_indicators'][0]['measurement_sources'] == [observation]
    assert saved['risk_analysis'] == previous['model']['risk_analysis']
    assert saved['monitoring']['pair_results'] == previous['model']['monitoring']['pair_results']
    assert freshness.analysis_status(saved, inputs) == 'current'


def test_extraction_policy_change_does_not_reuse_old_document_cache():
    from kodame_intake.performance_delta import enrich
    rows = documents()[1:]
    rows[0]['original_name'] = 'evidence.pdf'
    rows[0]['analysis'].update(pdm_measurements={'digest': 'legacy'}, pdm_measurement_cache={'legacy': {}})
    indicator = {'id': 'outputs-1', 'indicator': '양성 인원 (명)', 'evidence': '수료 명단',
                 'actual': '-', 'target': '-', 'evidence_document_ids': ['evidence']}
    plan = {'source_document_id': 'pdm', 'mappings': {'outputs-1': ['evidence']},
            'new_mappings': {'outputs-1': ['evidence']}, 'force_measurement_recheck': True}
    def extract(document, indicators, **kwargs):
        assert 'pdm_measurements' not in document['analysis']
        assert 'pdm_measurement_cache' not in document['analysis']
        assert document['analysis']['registration_facts']
        return []
    with patch('kodame_intake.pdm_evidence.extract_measurements', side_effect=extract) as ai:
        result = enrich([indicator], rows, plan, None)
    assert ai.call_count == 1 and result['new_pair_count'] == 1
