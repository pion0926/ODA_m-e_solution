"""Report boundaries preserve observed merit independently of evidence confidence."""
from copy import deepcopy
import json
from unittest.mock import MagicMock

import pytest

from backend.oda_me.reports.context import structured_slots_to_json
from kodame_intake import project_lifecycle
from kodame_intake import report_generator as generator
from kodame_intake.hwpx_pipeline import prepare_hwpx_sections
from kodame_intake.report_evaluation_context import for_report
from kodame_intake.report_score_validation import observed_score_issues
from kodame_intake.report_recovery import repair_recovery_response


CRITERIA=('relevance','coherence','effectiveness','efficiency','sustainability')
SECTION={'part_id':'criteria-effectiveness','section_number':17,'title':'효과성',
         'prompt':'현재 합성 사업의 확인된 성과와 증빙 한계를 구분함.',
         'required_inputs':[],'content':''}


def evaluations(*, score=2, evidence_status='needs_evidence'):
    return [{'criterion_id':key,'criterion_name':key,'score':score,
             'question_assessments':[{
                 'question_id':key+'-q1','score':score,
                 'finding':'확인된 활동과 일부 성과를 평가하되 증빙은 추가 확보가 필요함.',
                 'scoring_trace':{'assessment_basis':'provisional_document_review',
                     'selected_score':score,'status':'proposed' if score is not None else evidence_status,
                     'evidence_status':evidence_status,'coverage':0.4,'confidence':58},
                 'evidence_quotes':[{'document_id':'synthetic-document','quote':'합성 검토 원문'}],
             }]} for key in CRITERIA]


@pytest.mark.parametrize('evidence_status',['needs_evidence','needs_review','conflicted'])
def test_low_evidence_context_and_export_grade_keep_observed_two(evidence_status):
    rows=evaluations(evidence_status=evidence_status);before=deepcopy(rows)
    context=for_report(rows)
    question=context[2]['question_assessments'][0]
    assert context[2]['score']==question['score']==question['scoring_trace']['selected_score']==2
    assert question['scoring_trace']['coverage']==0.4
    assert question['scoring_trace']['confidence']==58
    assert question['scoring_trace']['evidence_status']==evidence_status
    assert 'evidence_quotes' not in question
    assert question['validated_source_references']==[{'document_id':'synthetic-document'}]

    # An AI-proposed hold cannot replace the saved numeric grade cells.
    wrong=structured_slots_to_json('grade',{'effectiveness_output_score':'판정보류',
        'effectiveness_total_score':'판정보류','overall_score':'판정보류'})
    bound=generator._ensure_official_grade_statement('grade',wrong,rows)
    prepared,_=prepare_hwpx_sections({}, {'grade':bound}, [],selected_parts={'grade'})
    slots=json.loads(prepared['grade'])['slots']
    assert slots['effectiveness_output_score']=='2점'
    assert slots['effectiveness_total_score']=='2점'
    assert slots['overall_score']=='10/20점 (잠정)'
    assert generator._official_grade_context(rows)['total_score']==10
    assert rows==before


@pytest.mark.parametrize('part,text',[
    ('criteria-effectiveness','효과성 점수는 판정보류임.'),
    ('criteria-effectiveness','효과성의 평가 점수는 자료 부족으로 판정 보류임.'),
    ('criteria-effectiveness','해당 기준 점수는 근거가 부족하여 보류임.'),
    ('summary-ko','이번 효과성 판정은 보류임.'),
    ('conclusion','종합점수는 판정보류임.'),
    ('conclusion','전체 평가 점수는 보류임.'),
    ('conclusion','종합 평가등급은 판정보류임.'),
    ('criteria-effectiveness','이전에는 판정보류였지만 현재 효과성 점수는 판정보류임.'),
    ('criteria-effectiveness','효과성의 두 번째 질문은 미확인이지만 효과성 점수는 판정보류임.'),
    ('criteria-effectiveness','효과성의 두 번째 질문은 미확인이며 기준 점수는 판정보류임.'),
])
def test_observed_scores_cannot_be_demoted_to_current_criterion_or_total_hold(part,text):
    rows=evaluations()
    assert observed_score_issues(part,text,rows)
    assert any('보류로 바' in issue for issue in generator._quantitative_consistency_issues(part,text,rows))


@pytest.mark.parametrize('text',[
    '효과성 점수는 2점이며 근거 확보율 40%, 증거 신뢰도 58%로 추가 증빙이 필요함.',
    '효과성의 추가 검증은 자료 확보까지 보류함. 현재 점수는 2점임.',
    '증빙이 부족하여 효과성의 신뢰도는 낮음. 성과 수준은 2점임.',
    '이전 평가에서 효과성 점수는 판정보류였음. 현재는 2점임.',
    '과거 자체평가의 종합점수는 판정보류였음.',
    '효과성 점수는 판정보류가 아니라 2점임.',
    '효과성 점수는 판정보류로 처리하지 않음.',
    '효과성 점수를 판정보류로 바꾸지 않음.',
    '효과성의 두 번째 질문은 판정보류이며 확인된 질문의 점수를 별도로 제시함.',
    '효과성의 두 번째 질문 평가 점수는 판정보류임. 효과성 기준 점수는 2점임.',
])
def test_evidence_caveats_historical_holds_negations_and_null_questions_remain_allowed(text):
    rows=evaluations()
    rows[2]['question_assessments'].append({'question_id':'effectiveness-q2','score':None})
    assert observed_score_issues('criteria-effectiveness',text,rows)==[]


def test_known_grade_slots_reject_holds_but_unknown_individual_question_is_allowed():
    rows=evaluations()
    rows[2]['question_assessments'].append({'question_id':'effectiveness-q2','score':None})
    wrong=structured_slots_to_json('grade',{'effectiveness_total_score':'판정보류',
        'overall_score':'판정보류','koica_grade':'판정보류','government_grade':'판정보류'})
    assert len(observed_score_issues('grade',wrong,rows))==4
    correct=structured_slots_to_json('grade',{'effectiveness_total_score':'2점',
        'effectiveness_outcome_score':'판정보류','overall_score':'10/20점'})
    assert observed_score_issues('grade',correct,rows)==[]
    rows[2]['score']=None
    assert observed_score_issues('criteria-effectiveness','효과성 점수는 판정보류임.',rows)==[]
    assert observed_score_issues('conclusion','종합점수는 판정보류임.',rows)==[]


def test_observed_score_contradiction_uses_existing_bounded_repair_without_score_invention():
    rows=evaluations();calls=[]
    validate=lambda text:generator._quantitative_consistency_issues('criteria-effectiveness',text,rows)
    corrected='효과성 점수는 2점이며 증빙 보완이 필요함.'
    def repair(content,issues):
        calls.append(issues)
        return corrected
    final,issues,attempts=repair_recovery_response('효과성 점수는 판정보류임.',validate,repair,lambda text:text)
    assert final==corrected and not issues and attempts==len(calls)==1
    _,issues,attempts=repair_recovery_response('효과성 점수는 판정보류임.',validate,
        lambda content,issues:content,lambda text:text)
    assert issues and attempts==2


def test_all_unobserved_scores_stay_null_and_cannot_gain_invented_grade():
    rows=evaluations(score=None)
    assert all(row['score'] is None for row in for_report(rows))
    wrong=structured_slots_to_json('grade',{'effectiveness_output_score':'2점',
        'effectiveness_total_score':'2점','overall_score':'10/20점','koica_grade':'C'})
    assert generator._quantitative_consistency_issues('grade',wrong,rows)
    bound=generator._ensure_official_grade_statement('grade',wrong,rows)
    slots=json.loads(bound)['slots']
    for key in ('effectiveness_output_score','effectiveness_total_score',
                'overall_score','koica_grade','government_grade'):
        assert slots[key]=='판정보류'
    assert generator._official_grade_context(rows)=={}


class PromptCaptured(BaseException):
    """Stop before any provider call or persistence, including fallback handlers."""


def prompt_context(prompt, heading):
    value=prompt.split(heading+'\n',1)[1]
    return json.JSONDecoder().raw_decode(value[value.index('[{'):])[0]


@pytest.mark.parametrize('score',[2,None])
@pytest.mark.parametrize('stage',['draft','quality','recovery'])
def test_actual_ai_request_paths_distinguish_numeric_merit_and_unknown_score(monkeypatch,stage,score):
    rows=evaluations(score=score);overview={'country':{'text':'합성국'}}
    captured=[]
    def capture(system,prompt,*args,**kwargs):
        captured.append(prompt)
        raise PromptCaptured()
    monkeypatch.setattr(generator,'_call_json',capture)
    monkeypatch.setattr(generator,'_section_few_shot_messages',lambda *args,**kwargs:[])
    if stage=='quality':
        captured.append(generator._quality_prompt(SECTION,[],[],overview,rows,[],{},'합성 초안'))
    elif stage=='recovery':
        with pytest.raises(PromptCaptured):
            generator._grounded_fallback(SECTION,[],overview,rows,[],{},'')
    else:
        connection=MagicMock();conn=connection.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.return_value=deepcopy(SECTION)
        monkeypatch.setattr(generator,'connection',connection)
        monkeypatch.setattr(generator,'OPENROUTER_API_KEY','synthetic-no-provider-call')
        monkeypatch.setattr(project_lifecycle,'capture_input_snapshot',lambda:{})
        monkeypatch.setattr(generator,'section_documents',lambda *args,**kwargs:[])
        monkeypatch.setattr(generator,'evidence_packet',lambda *args,**kwargs:[])
        monkeypatch.setattr(generator,'reference_examples',lambda *args,**kwargs:[])
        monkeypatch.setattr(generator,'_context_for',lambda *args:(overview,rows,[]))
        monkeypatch.setattr(generator,'_verified_execution_scope',lambda *args:{})
        monkeypatch.setattr(generator,'_project_source_names',lambda:[])
        with pytest.raises(PromptCaptured):
            generator._generate_report_section('criteria-effectiveness')
    assert len(captured)==1
    prompt=captured[0]
    assert 'score가 숫자이면' in prompt and '그 점수를 유지한다' in prompt
    assert '증빙 보완 정보' in prompt and '점수 보류로 바꾸지 않는다' in prompt
    assert 'score=null은' in prompt and '0점' in prompt
    projected=prompt_context(prompt,'[저장된 평가결과]' if stage=='recovery' else '[최신 평가결과]')
    assert projected[2]['score']==score
    question=projected[2]['question_assessments'][0]
    assert question['score']==score
    assert question['scoring_trace']['evidence_status']=='needs_evidence'
    assert question['scoring_trace']['coverage']==0.4 and question['scoring_trace']['confidence']==58
    assert 'evidence_quotes' not in question
