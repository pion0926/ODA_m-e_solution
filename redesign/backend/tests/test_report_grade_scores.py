import json
from kodame_intake.report_grade_scores import bind_grade_question_slots
from kodame_intake.report_generator import _ensure_official_grade_statement
from backend.oda_me.reports.context import structured_slots_to_json


def test_question_identity_overrides_shuffled_ai_scores_and_preserves_holds():
    evaluations = [
        {'criterion_id': 'coherence', 'score': 2.5, 'question_assessments': [
            {'question_id': 'coherence-q2', 'score': 3, 'finding': '외부 기관과의 조율 근거가 확인됨.'},
            {'question_id': 'coherence-q1', 'score': 2, 'finding': '내적 조율 근거가 제한적임.'}]},
        {'criterion_id': 'effectiveness', 'score': None, 'question_assessments': [
            {'question_id': 'effectiveness-q1', 'score': 3, 'finding': '산출물 달성의 근거가 확인됨.'},
            {'question_id': 'effectiveness-q2', 'score': None, 'finding': '성과는 추적자료 확보 후 판단해야 함.'},
            {'question_id': 'effectiveness-q3', 'score': None, 'finding': '형평성은 분리자료가 부족함.'}]},
    ]
    wrong = {'coherence_internal_score': '3점', 'coherence_external_score': '2점',
             'effectiveness_output_score': '판정보류', 'effectiveness_equity_score': '3점'}
    actual = bind_grade_question_slots(wrong, evaluations)
    assert actual['coherence_internal_score'] == '2점'
    assert actual['coherence_external_score'] == '3점'
    assert actual['effectiveness_output_score'] == '3점'
    assert actual['effectiveness_equity_score'] == '판정보류'
    assert actual['effectiveness_total_score'] == '판정보류'
    assert actual['coherence_internal_reason'] == '내적 조율 근거가 제한적임.'
    assert actual['effectiveness_equity_reason'] == '형평성은 분리자료가 부족함.'
    final = json.loads(_ensure_official_grade_statement('grade', structured_slots_to_json('grade', wrong), evaluations))['slots']
    assert final['overall_score'] == '판정보류'
    assert final['coherence_total_score'] == '2.5점'


def test_missing_question_never_inherits_ai_or_criterion_score():
    actual = bind_grade_question_slots({'efficiency_balance_score': '4점'}, [
        {'id': 'efficiency', 'score': None, 'question_assessments': []}])
    assert actual['efficiency_balance_score'] == '판정보류'


def test_held_scores_do_not_acquire_numeric_units_in_hwpx():
    from backend.oda_me.hwpx.formatting import format_score
    assert format_score(None, '점') == '판정보류'
    assert format_score(None, '/20점') == '판정보류'
    assert format_score(2.5, '점') == '2.5점'
    assert format_score(15, '/20점') == '15/20점'


def test_long_findings_fit_grade_reason_cell_budget():
    result = bind_grade_question_slots({}, [{'id':'relevance','score':3,'question_assessments':[
        {'question_id':'relevance-q1','score':3,'finding':'현재 자료에서 확인되는 사업 설계와 정책 정합성의 근거를 종합하여 검토함. ' * 20}]}])
    assert len(result['relevance_policy_reason']) <= 101


def test_long_sentence_keeps_limitation_and_never_invents_a_closing_fragment():
    from backend.oda_me.hwpx.patchers import grade_question_reason
    positive = '현재시점 문헌기반 평가에서 ' + '교육과정 운영 및 관계기관 협의와 제도 승인 경로의 연결, ' * 4 + '일부 실행이 확인된다.'
    limitation = '다만 비교 가능한 종료선과 현지 단독 운영 자료가 없어 1.7점으로 평가한다.'
    result = grade_question_reason(positive + ' ' + limitation, 90)
    assert result == positive + ' ' + limitation
    assert '해당 사실을 질문별' not in result
    assert len(result) > 90


def test_grade_reason_without_sentence_delimiters_is_not_cut_at_character_limit():
    from backend.oda_me.hwpx.patchers import grade_question_reason
    reason = '확인한 자료와 목표의 범위를 교차 대조하고 ' * 8 + '추가 검증이 필요함'
    assert grade_question_reason(reason, 90) == reason + '.'
