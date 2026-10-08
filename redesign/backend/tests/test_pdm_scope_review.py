import copy
from unittest.mock import patch

import pytest

from kodame_intake.pdm_scope_review import needs_scope_review, review_scope, review_reference_scopes
from kodame_intake.openrouter import (AnalysisError, BillingError, ConfigurationError,
                                      MissingApiKey, ProviderTransientError, RefusalError)
from kodame_intake.ai.job_budget import BudgetExceeded
from kodame_intake.intake_control import IntakeStopped


ITEM = {'indicator_id': 'outputs-3-1-1', 'confidence': .96, 'evidence_kind': 'direct_record',
        'measurement_relation': 'reported_result', 'subject_match': True, 'activity_match': True,
        'scope_match': False, 'evidence_quote': '지역 강사 양성: 목표 10명, 실적 6명. 수료명단 6명.',
        'proves': '지역 강사 양성 실적 6명을 보고함', 'rationale': '강사 양성 실적 표에 기재됨',
        'limitations': '강사 자격증 대장 원본과 제3자 확인 자료가 첨부되지 않았다.'}
INDICATOR = {'id': 'outputs-3-1-1', 'text': '양성된 지역 강사 수(명)',
             'mov': '강사 자격증 발급 대장', 'tier': 'outputs'}
CONTEXT = {'plan_text': '등록된 지역 강사 양성 사업이다.', 'indicators': [INDICATOR]}


def test_reported_result_scope_recheck_does_not_rewrite_original_evidence():
    original = copy.deepcopy(ITEM)
    with patch('kodame_intake.pdm_scope_review._request_json', return_value=(
            {'scope_match': True, 'reason': '등록 사업의 동일한 지역 강사 양성 인원에 대한 실적 보고입니다.'}, 'test')) as request:
        result = review_scope(original, INDICATOR, CONTEXT)
    assert original == ITEM
    assert result['scope_match'] is True
    assert result['scope_review']['initial_scope_match'] is False
    for key in ('evidence_quote', 'confidence', 'proves', 'limitations', 'measurement_relation'):
        assert result[key] == original[key]
    assert request.call_count == 1
    assert request.call_args.kwargs['response_schema']['properties']['scope_match'] == {'type': 'boolean'}


def test_different_project_or_population_stays_reference():
    with patch('kodame_intake.pdm_scope_review._request_json', return_value=(
            {'scope_match': False, 'reason': '다른 지역에서 수행한 별도 사업의 강사 양성 인원입니다.'}, 'test')):
        matches, reviewed = review_reference_scopes({'pdm': [], 'pdm_references': [ITEM], 'registration_facts': {'facts': []}}, CONTEXT)
    assert reviewed == 1 and not matches['pdm']
    assert matches['pdm_references'][0]['scope_match'] is False
    assert not needs_scope_review(matches['pdm_references'][0])


@pytest.mark.parametrize('change', [{'measurement_relation': 'prerequisite'}, {'measurement_relation': 'target'},
    {'subject_match': False}, {'activity_match': False}, {'confidence': .74}, {'scope_match': True},
    {'evidence_quote': ''}])
def test_only_high_confidence_reported_result_with_scope_conflict_is_reviewed(change):
    item = {**ITEM, **change}
    with patch('kodame_intake.pdm_scope_review._request_json') as request:
        assert review_scope(item, INDICATOR, CONTEXT) == item
    request.assert_not_called()


def test_provider_failure_preserves_registration_and_reference_after_bounded_retry():
    with patch('kodame_intake.pdm_scope_review._request_json', side_effect=AnalysisError('provider failed')) as request:
        matches, count = review_reference_scopes({'pdm': [], 'pdm_references': [ITEM]}, CONTEXT)
    assert count == 1 and request.call_count == 2
    assert not matches['pdm'] and matches['pdm_references'][0]['scope_match'] is False
    assert matches['pdm_references'][0]['scope_review']['status'] == 'unavailable'
    assert 'provider failed' not in str(matches['pdm_references'][0]['scope_review'])


@pytest.mark.parametrize('error_type', [ProviderTransientError, BillingError,
    ConfigurationError, RefusalError, MissingApiKey])
def test_terminal_provider_condition_preserves_reference_without_extra_retry(error_type):
    with patch('kodame_intake.pdm_scope_review._request_json', side_effect=error_type('private provider details')) as request:
        result = review_scope(ITEM, INDICATOR, CONTEXT)
    assert request.call_count == 1 and result['scope_match'] is False
    assert result['scope_review']['status'] == 'unavailable'
    assert result['scope_review']['error_type'] == error_type.__name__
    assert 'private provider details' not in str(result['scope_review'])


@pytest.mark.parametrize('error_type', [BudgetExceeded, IntakeStopped])
def test_explicit_cancellation_and_budget_boundaries_are_not_swallowed(error_type):
    with patch('kodame_intake.pdm_scope_review._request_json', side_effect=error_type('stop')) as request:
        with pytest.raises(error_type):
            review_scope(ITEM, INDICATOR, CONTEXT)
    assert request.call_count == 1


@pytest.mark.parametrize('bad', [{'scope_match': 'true', 'reason': '같은 사업의 같은 측정 집단 실적입니다.'},
                               {'scope_match': True, 'reason': ''}, {}])
def test_invalid_response_cannot_promote_reference(bad):
    with patch('kodame_intake.pdm_scope_review._request_json', return_value=(bad, 'test')) as request:
        result = review_scope(ITEM, INDICATOR, CONTEXT)
    assert request.call_count == 2 and result['scope_match'] is False
    assert result['scope_review']['status'] == 'unavailable'


def test_prepared_repair_only_changes_verified_reference_and_is_idempotent():
    target = {**ITEM, 'indicator_id': 'other', 'measurement_relation': 'target'}
    original = {'pdm': [], 'pdm_references': [ITEM, target],
                'registration_facts': {'facts': [{'statement': '기존 보존 사실'}]}}
    with patch('kodame_intake.pdm_scope_review._request_json', return_value=(
            {'scope_match': True, 'reason': '등록된 사업의 지표와 동일한 측정 대상 및 활동 인원입니다.'}, 'test')) as request:
        fixed, count = review_reference_scopes(original, CONTEXT)
        second, second_count = review_reference_scopes(fixed, CONTEXT)
    assert original['pdm'] == [] and count == 1
    assert len(fixed['pdm']) == 1 and fixed['pdm_references'] == [target]
    assert fixed['registration_facts'] == original['registration_facts']
    assert second == fixed and second_count == 0 and request.call_count == 1
