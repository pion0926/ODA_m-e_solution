"""A removed but previously verified pair is manually restorable without new AI."""
import copy
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from kodame_intake.performance_delta import enrich, fingerprint
from kodame_intake.performance_review import build_plan, save_overrides, validate_selection
from kodame_intake.performance_targets import TARGET_SELECTION_VERSION
from kodame_intake.pdm_evidence import MEASUREMENT_VERSION
from kodame_intake.pdm_mapping_policy import VERSION
from kodame_intake.llm_models import current_llm_model


INDICATOR = {'id': 'i', 'text': '교원 양성 인원 수 (명)', 'mov': '수료자 명단'}
PERFORMANCE = {'id': 'i', 'indicator': INDICATOR['text'], 'evidence': INDICATOR['mov'],
               'target': '-', 'actual': '-', 'evidence_document_ids': [], 'measurement_sources': [],
               'target_selection': {'version': TARGET_SELECTION_VERSION}}


def source_document(key, role='evidence'):
    return {'id': key, 'original_name': key, 'status': 'completed', 'upload_role': role,
            'sha256': key, 'progress': 100, 'analysis': {}}


def stored_model():
    observation = {'kind': 'actual', 'value': '4명', 'period': '2026', 'document_id': 'old',
                   'indicator_id': 'i', 'file_name': 'old', 'quote': '수료자 4명'}
    return {'id': 'model', 'source_document_id': 'pdm', 'model': {
        'performance_indicators': [copy.deepcopy(PERFORMANCE)],
        'monitoring': {'reviewed_mappings': {'i': []}, 'pair_results': {
            fingerprint('pdm', source_document('old'), INDICATOR): {
                'document_id': 'old', 'indicator_id': 'i', 'measurement_version': MEASUREMENT_VERSION,
                'model': current_llm_model(),
                'observations': [observation], 'reviews': [{'indicator_id': 'i', 'status': 'found'}]}}}}}


def plan():
    return {'ready': True, 'revision': 'r', 'message': '', 'source_document_id': 'pdm',
            'source_file_name': 'pdm', 'input_snapshot': {}, 'baseline_model_id': 'model',
            'documents': [source_document(key) for key in ('old', 'retained', 'new')],
            'indicators': [{**INDICATOR, 'document_ids': [], 'retained_document_ids': ['retained'],
                            'analyzed_document_ids': ['old', 'retained'], 'restorable_document_ids': ['old']}],
            'mapping_changed_indicator_ids': []}


def test_build_plan_exposes_only_unlinked_valid_history_for_optional_restore():
    rows = [source_document('pdm', 'pdm'), source_document('old'), source_document('unknown')]
    rows[1]['analysis']['pdm_mapping_overrides'] = {'version': VERSION, 'source_document_id': 'pdm',
                                                  'included': [], 'excluded': ['i']}
    saved = stored_model()
    conn = Mock()
    conn.execute.return_value.fetchall.return_value = rows
    conn.execute.return_value.fetchone.side_effect = [saved, None]
    with patch('kodame_intake.performance_review.foundation_state', return_value={'ready': True}), \
         patch('kodame_intake.performance_review.capture_input_snapshot', return_value={}), \
         patch('kodame_intake.pdm_monitoring._model_from_slots', return_value={
             'tiers': [{'id': 'outputs', 'name': '산출물', 'indicators': [INDICATOR]}]}):
        preview = build_plan(conn)
    item = preview['indicators'][0]
    assert item['document_ids'] == []
    assert item['retained_document_ids'] == []
    assert item['restorable_document_ids'] == ['old']
    # Explicit exclusion is not silently overridden by opening the preview.
    assert rows[1]['analysis']['pdm_mapping_overrides']['excluded'] == ['i']


def test_restore_is_separate_from_new_analysis_and_retains_connected_history():
    reviewed = validate_selection(plan(), 'r', {'i': ['old', 'new']})
    assert reviewed['mappings'] == {'i': ['new', 'old', 'retained']}
    assert reviewed['new_mappings'] == {'i': ['new']}
    assert reviewed['restored_mappings'] == {'i': ['old']}
    assert reviewed['mapping_changed_indicator_ids'] == ['i']


def test_restore_only_executes_without_forcing_new_pair_or_remaining_deferred():
    current = plan()
    current['deferred_mappings'] = {'i': ['old']}
    reviewed = validate_selection(current, 'r', {'i': ['old']})
    assert reviewed['new_mappings'] == {'i': []}
    assert reviewed['deferred_mappings'] == {'i': []}
    rows = [source_document('old'), source_document('retained')]
    item = {**copy.deepcopy(PERFORMANCE), 'evidence_document_ids': ['old', 'retained']}
    with patch('kodame_intake.pdm_evidence.extract_measurements') as ai:
        result = enrich([item], rows, reviewed, stored_model())
    ai.assert_not_called()
    assert item['actual'] == '4명'
    assert item['selected_measurements']['actual']['document_id'] == 'old'
    assert result['new_pair_count'] == 0 and result['restored_pair_count'] == 1
    assert not item['mapping_review_required']


def test_already_connected_pair_still_cannot_be_requested_again():
    with pytest.raises(HTTPException) as error:
        validate_selection(plan(), 'r', {'i': ['retained']})
    assert error.value.status_code == 409


def test_unselected_restore_remains_excluded_and_empty_rerun_is_rejected():
    with pytest.raises(HTTPException) as error:
        validate_selection(plan(), 'r', {'i': []})
    assert error.value.status_code == 409


def test_explicit_restore_overrides_only_that_manual_exclusion():
    current = plan()
    current['documents'] = [source_document('old')]
    reviewed = validate_selection(current, 'r', {'i': ['old']})
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = {'analysis': {'pdm_mapping_overrides': {
        'version': VERSION, 'source_document_id': 'pdm', 'included': [], 'excluded': ['i', 'another']}}}
    save_overrides(conn, current, reviewed)
    payload = conn.execute.call_args.args[1][0].obj
    assert payload['included'] == ['i']
    assert payload['excluded'] == ['another']


def test_not_selecting_restorable_history_preserves_user_exclusion():
    current = plan()
    current['documents'] = [source_document('old')]
    current['mapping_changed_indicator_ids'] = ['i']
    reviewed = validate_selection(current, 'r', {'i': []})
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = {'analysis': {'pdm_mapping_overrides': {
        'version': VERSION, 'source_document_id': 'pdm', 'included': [], 'excluded': ['i']}}}
    save_overrides(conn, current, reviewed)
    payload = conn.execute.call_args.args[1][0].obj
    assert payload['included'] == [] and payload['excluded'] == ['i']
    assert reviewed['restored_mappings'] == {'i': []}


def test_invalidated_history_still_requires_fresh_analysis():
    current = plan()
    current['indicators'][0]['analyzed_document_ids'] = ['retained']
    current['indicators'][0]['restorable_document_ids'] = []
    reviewed = validate_selection(current, 'r', {'i': ['old']})
    assert reviewed['new_mappings'] == {'i': ['old']}
    assert reviewed['restored_mappings'] == {'i': []}


def test_foreign_or_excluded_document_cannot_be_restored():
    current = plan()
    current['documents'] = [doc for doc in current['documents'] if doc['id'] != 'old']
    with pytest.raises(HTTPException) as error:
        validate_selection(current, 'r', {'i': ['old']})
    assert error.value.status_code == 422
