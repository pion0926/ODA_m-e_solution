"""Whole-project cost/time caps never leak from individual budget lines."""
from unittest.mock import patch

import pytest

import test_dac_rules as fixtures
from kodame_intake.dac_rules import RULES, score_question
from kodame_intake.dac_measurements import calculate
from kodame_intake.dac_rules import refs_for


def fixture(qid='efficiency-q1', *, scope='whole_project', justification='asserted'):
    item, evidence = fixtures.DacRuleEngineTests().fixture(qid)
    quote = '전체 사업 총예산은 최초 100원에서 실제 160원이 되었다. 승인된 변경 사유와 비효율 원인을 별도 확인한다.'
    evidence['E1']['quote'] = quote
    measurement = {'metric': '전체 사업 예산', 'target': 100, 'actual': 160,
        'unit': '원', 'period': '전체 사업기간', 'population': '사업 전체',
        'direction': 'budget', 'comparable': True, 'due': True,
        'measurement_scope': scope, 'scope_quote': quote,
        'target_evidence_ids': ['E1'], 'actual_evidence_ids': ['E1'],
        'justification': justification, 'justification_evidence_ids': ['E1']}
    item['indicators'][0]['measurements'] = [measurement]
    return item, evidence, measurement


@pytest.mark.parametrize('qid', list(RULES['questions']))
def test_component_overrun_cannot_cap_any_question_at_one(qid):
    item, evidence, measurement = fixture(qid, scope='component')
    measurement['metric'] = '학생인건비'
    item['red_flag']['status'] = 'unverified'
    result = score_question(qid, item, evidence)
    assert 'BUDGET_DURATION_150' not in [cap['rule'] for cap in result['applied_rules']]
    assert result['selected_score'] != 1


@pytest.mark.parametrize('qid', [qid for qid in RULES['questions'] if qid != 'efficiency-q1'])
def test_whole_project_budget_cap_is_not_another_questions_rule(qid):
    item, evidence, _ = fixture(qid, justification='verified')
    result = score_question(qid, item, evidence)
    assert 'BUDGET_DURATION_150' not in [cap['rule'] for cap in result['applied_rules']]


@pytest.mark.parametrize('direction', ['budget', 'duration'])
def test_confirmed_whole_project_overrun_with_verified_reason_has_two_ceiling(direction):
    item, evidence, measurement = fixture(justification='verified')
    measurement['direction'] = direction
    if direction == 'duration':
        evidence['E1']['quote'] = measurement['scope_quote'] = '전체 사업기간은 최초 100일에서 실제 160일이 되었다. 승인된 변경 사유가 있다.'
    item['indicators'][1 if direction == 'duration' else 0]['measurements'] = [measurement]
    result = score_question('efficiency-q1', item, evidence)
    assert result['selected_score'] == 2
    assert any(c['rule'] == 'BUDGET_DURATION_150' and c['maximum'] == 2 for c in result['applied_rules'])


def test_missing_approval_does_not_prove_unjustified_overrun():
    item, evidence, _ = fixture(justification='asserted')
    item['red_flag']['status'] = 'unverified'
    result = score_question('efficiency-q1', item, evidence)
    assert result['selected_score'] != 1
    assert 'BUDGET_DURATION_150' not in [cap['rule'] for cap in result['applied_rules']]


def test_confirmed_adverse_whole_project_overrun_still_scores_one():
    item, evidence, _ = fixture(justification='none')
    item['red_flag']['status'] = 'met'
    result = score_question('efficiency-q1', item, evidence)
    assert result['selected_score'] == 1
    assert any(c['rule'] == 'BUDGET_DURATION_150' and c['maximum'] == 1 for c in result['applied_rules'])


@pytest.mark.parametrize('change', [{'measurement_scope': 'component'}, {'measurement_scope': 'unknown'},
    {'scope_quote': ''}, {'scope_quote': '없는 전체 사업 범위를 만들어낸 설명'},
    {'due': False}, {'comparable': False}, {'actual': 999}])
def test_incomplete_scope_or_measurement_cannot_trigger_project_cap(change):
    item, evidence, measurement = fixture()
    measurement.update(change)
    result = score_question('efficiency-q1', item, evidence)
    assert 'BUDGET_DURATION_150' not in [cap['rule'] for cap in result['applied_rules']]
    item['red_flag']['status'] = 'met'
    with pytest.raises(ValueError, match='전체 사업'):
        score_question('efficiency-q1', item, evidence)


def test_unverified_check_never_leaks_its_other_measurements_into_caps():
    item, evidence, measurement = fixture()
    item['indicators'][0]['measurements'].append({**measurement, 'actual': 999})
    result = score_question('efficiency-q1', item, evidence)
    assert result['checks'][0]['state'] == 'unverified'
    assert 'BUDGET_DURATION_150' not in [cap['rule'] for cap in result['applied_rules']]


def test_provider_cannot_assert_scope_validation_or_use_another_questions_quote():
    _, evidence, measurement = fixture()
    measurement.update(scope_quote='원문에 없는 전체 사업 범위', scope_validated=True)
    result = calculate([measurement], evidence, 'efficiency-q1', refs_for)[0]
    assert result['scope_validated'] is False
    assert result['ratio'] == 1.6  # Preserve the grounded observation, not the unjustified global cap.


@pytest.mark.parametrize('quote', [
    '학생인건비는 1차년도 100원에서 160원으로 증가하였다. 해당 비목의 증액 집행이다.',
    'Annual student salary budget was 100 and actual expenditure was 160.',
    '알려지지 않은 언어의 수치 비교 100 160',
])
def test_mislabelled_component_and_unknown_scope_cannot_trigger_project_cap(quote):
    item, evidence, measurement = fixture()
    evidence['E1']['quote'] = measurement['scope_quote'] = quote
    result = score_question('efficiency-q1', item, evidence)
    assert result['checks'][0]['measurements'][0]['scope_validated'] is False
    assert 'BUDGET_DURATION_150' not in [cap['rule'] for cap in result['applied_rules']]
    measurement['target'], measurement['actual'] = 100, 290
    evidence['E1']['quote'] = measurement['scope_quote'] = '학생인건비는 100원에서 290원으로 증가하여 290% 집행하였다.'
    result = score_question('efficiency-q1', item, evidence)
    assert result['checks'][0]['measurements'][0]['scope_validated'] is False
    assert result['selected_score'] != 1


@pytest.mark.parametrize('direction,quote', [
    ('budget', 'The total project budget was 100 and the actual whole project cost was 160.'),
    ('duration', 'The overall project duration was originally 100 days and became 160 days.'),
])
def test_explicit_english_project_boundary_is_supported(direction, quote):
    _, evidence, measurement = fixture()
    evidence['E1']['quote'] = measurement['scope_quote'] = quote
    measurement['direction'] = direction
    result = calculate([measurement], evidence, 'efficiency-q1', refs_for)[0]
    assert result['scope_validated'] is True


def test_judgment_prompt_upgrade_invalidates_replay_without_changing_extraction_rules():
    from kodame_intake import dac_replay, dac_evidence
    from kodame_intake.dac_rules import RULE_DIGEST, PROMPT_VERSION
    with patch.object(dac_replay, 'connection') as conn:
        conn.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
        new = dac_replay.fingerprint([], 'same-model')
        with patch.object(dac_replay, 'PROMPT_VERSION', 'dac-fact-judgement-v14-contextual'):
            old = dac_replay.fingerprint([], 'same-model')
    assert new != old
    assert PROMPT_VERSION == 'dac-fact-judgement-v15-scope-conflict'
    assert RULE_DIGEST == dac_evidence.RULE_DIGEST == '562164e5bf9722da9f882a0c96cf877dbd46774684ec0a816cf0616b48daa812'
