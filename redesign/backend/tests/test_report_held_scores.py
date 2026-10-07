"""Held judgments cannot acquire fabricated scores during report generation."""
from copy import deepcopy
import json
import pytest

from kodame_intake.report_generator import _ensure_official_grade_statement, _quantitative_consistency_issues
from kodame_intake.report_score_validation import held_score_issues
from kodame_intake.report_recovery import repair_recovery_response


ROWS=[{'criterion_id':key,'score':score,'question_assessments':[{'scoring_trace':{'assessment_basis':'provisional_document_review'}}]}
      for key,score in [('relevance',3),('coherence',3),('effectiveness',2.7),('efficiency',1),('sustainability',None)]]


@pytest.mark.parametrize('text',[
    '종합점수는 9.7/20점이며 KOICA C등급으로 평가됨.',
    '현재 총점은 9.7점으로 산정됨.',
    '현재 KOICA 등급 C, 국무조정실 등급 성공적임.',
    '종합등급은 C등급임.',
    '국무조정실 등급은 부분 성공적임.',
    '종합점수는 판정보류임.\n종합점수는 9.7/20점임.',
    '이전 평가 12/20점이었음. 그러나 현재 종합점수는 9.7/20점임.',
    '과거 평가와 비교한 현재 총점은 9.7점임.',
    '종합점수는 9.7/20점이며, 최종 등급은 확정하지 않음.',
])
def test_current_total_and_grade_claims_rejected_even_after_hold_notice(text):
    ensured=_ensure_official_grade_statement('conclusion',text,ROWS)
    assert '판정보류' in ensured
    assert _quantitative_consistency_issues('conclusion',ensured,ROWS)


@pytest.mark.parametrize('part,text',[
    ('criteria-sustainability','지속가능성 점수는 1점임.'),
    ('criteria-sustainability','종합점수는 2.5점임.'),
    ('criteria-sustainability','종합 평가 2점으로 판정함.'),
    ('summary-ko','지속가능성은 0점으로 처리함.'),
    ('summary-ko','지속가능성 평가 점수: 2.5/4점'),
])
def test_held_criterion_cannot_gain_numeric_score(part,text):
    assert held_score_issues(part,text,ROWS)


@pytest.mark.parametrize('text',[
    '현재 종합점수와 등급은 판정보류임. 적절성 3점, 효과성 2.7점으로 검토됨.',
    '이전 평가에서는 종합점수가 12/20점이었음. 현재 종합점수는 판정보류임.',
    '과거 자체평가의 KOICA C등급은 참고자료이며, 현재 등급은 판정보류임.',
    '루브릭의 예시: 종합점수 12/20점, KOICA 등급 C. 현재 총점은 산정하지 않음.',
    '지속가능성 루브릭은 1~4점 척도로 구성됨.',
    '지속가능성의 첫 번째 질문은 2점, 두 번째 질문은 판정보류임.',
    '종합점수는 9.7/20점으로 확정하지 않음. 현재는 판정보류임.',
    '지속가능성 점수 1점으로 대체하지 않음.',
])
def test_historical_reference_scale_and_actual_subquestion_scores_are_allowed(text):
    assert held_score_issues('criteria-sustainability',text,ROWS)==[]


def test_fully_scored_previous_policy_unchanged_and_input_not_mutated():
    rows=deepcopy(ROWS);before=deepcopy(ROWS)
    rows[-1]['score']=2
    assert held_score_issues('conclusion','종합점수 11.7/20점',rows)==[]
    held_score_issues('conclusion','종합점수 11.7/20점',ROWS)
    assert ROWS==before


def test_structured_held_grade_slots_reject_zero_and_fabricated_band():
    issues=held_score_issues('grade',json.dumps({'slots':{'overall_score':'0/20점','koica_grade':'F',
        'government_grade':'미흡','sustainability_total_score':'1점'}}),ROWS)
    assert len(issues)>=4
    assert held_score_issues('grade',json.dumps({'slots':{key:'판정보류' for key in
        ('overall_score','koica_grade','government_grade','sustainability_total_score')}}),ROWS)==[]


def test_existing_recovery_rechecks_held_scores_and_has_finite_retries():
    validate=lambda content:held_score_issues('conclusion',content,ROWS)
    calls=[]
    def repair(content,issues):
        calls.append(issues)
        return '종합점수와 등급은 판정보류임.'
    final,issues,count=repair_recovery_response('종합점수 9.7/20점',validate,repair,lambda value:value)
    assert not issues and count==1 and calls
    assert '판정보류' in final
    calls.clear()
    final,issues,count=repair_recovery_response('종합점수 9.7/20점',validate,
        lambda content,issues: calls.append(issues) or content,lambda value:value)
    assert issues and count==2 and len(calls)==2
