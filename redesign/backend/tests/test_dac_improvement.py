from copy import deepcopy
import pytest
from kodame_intake.dac_improvement import build_improvement_guidance


def criterion(state='unverified', **extra):
    check = dict(id='Q1_I1', criterion='성과 검증', state=state, finding='평가기간의 성과 확인',
                 required_evidence='원시 측정자료', evidence_document_ids=['document-a'], **extra)
    return {'question_assessments': [{'question_id':'Q1', 'question':'성과가 지속되는가?',
        'score':None, 'scoring_trace':{'rubric_digest':'saved-v1', 'checks':[check],
                                     'four_point_gate':{'status':'met'}}}]}


@pytest.mark.parametrize('state,kind', [('unverified','evidence'), ('negative','performance'),
    ('limited','performance'), ('substantial','performance'), ('conflicted','review')])
def test_distinguishes_missing_evidence_from_failed_outcomes(state, kind):
    data = criterion(state)
    before = deepcopy(data)
    guide = build_improvement_guidance(data)
    assert guide['items'][0]['kind'] == kind
    assert guide['items'][0]['evidence_document_ids'] == ['document-a']
    assert data == before  # never rescore or mutate saved data
    assert '보장하지' in guide['notice']


@pytest.mark.parametrize('field', ['보건소 예방접종률', '농가 관개용수 접근률', '전자정부 민원 처리시간', '취업률'])
def test_guidance_uses_each_projects_own_criteria(field):
    data = criterion()
    data['question_assessments'][0]['scoring_trace']['checks'][0].update(
        criterion=field, required_evidence=field+' 원자료')
    result = build_improvement_guidance(data, stale=True)
    assert result['items'][0]['title'] == field
    assert result['items'][0]['required_evidence'] == field+' 원자료'
    assert result['is_stale']
    assert '교통대' not in str(result) and 'CPCR' not in str(result)


def test_measurements_caps_and_gate_are_not_hidden():
    data = criterion('unverified', measurements=[
        {'metric':'재난 사망률', 'validation_error':'원문 불일치'},
        {'metric':'민원 시간', 'due':False}])
    trace = data['question_assessments'][0]['scoring_trace']
    trace.update(applied_rules=[{'maximum':2,'reason':'평가기간 지연'}],
                 four_point_gate={'status':'unverified','finding':'독립 검증 필요'})
    result = build_improvement_guidance(data)
    titles = [item['title'] for item in result['items']]
    assert titles == ['민원 시간 · 비교 조건 확인','점수 상한 조건 확인','4점 필수 조건 확인',
                      '성과 검증','재난 사망률 · 원문 수치 확인']
    assert sum(result['counts'].values()) == 5


def test_verified_maintenance_and_quality_downgrade():
    assert build_improvement_guidance(criterion('verified'))['maintenance']
    assert build_improvement_guidance(criterion('substantial', proposed_state='verified'))['items'][0]['kind'] == 'evidence'
    assert build_improvement_guidance(criterion('verified', valid_evidence=False))['items'][0]['kind'] == 'evidence'


@pytest.mark.parametrize('data', [{}, {'question_assessments':None},
    {'question_assessments':[None, {'scoring_trace':None}]},
    {'question_assessments':[{'scoring_trace':{'rubric_digest':'v','checks':None}}]}])
def test_legacy_or_missing_results_do_not_claim_success(data):
    result = build_improvement_guidance(data)
    assert result['items'] and not result['maintenance']
    assert result['items'][0]['kind'] == 'review'
