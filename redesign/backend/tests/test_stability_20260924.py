import copy
import json
from unittest.mock import patch

import httpx
import pytest
from kodame_intake import openrouter as o, project_overview as overview
from kodame_intake.structured_output import parse_object
from kodame_intake.llm_models import llm_model_context
from kodame_intake import dac_assessor as dac
from kodame_intake.evaluation_criteria import EVALUATION_CRITERIA


def response(status=200, content='{"ok":true}', finish='stop', blocks=False):
    if blocks:
        content=[{'type':'text','text':content}]
    return httpx.Response(status,json={'choices':[{'message':{'content':content},'finish_reason':finish}]},
                          request=httpx.Request('POST','https://test.invalid'))


@pytest.mark.parametrize('model', ['openai/gpt-5.6-luna','google/gemini-3.5-flash-lite','anthropic/claude-haiku-4.5'])
def test_three_providers_same_contract_and_selected_model(model):
    schema={'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}
    with patch.object(o.httpx,'Client') as factory, patch.object(o,'OPENROUTER_API_KEY','test'), patch.object(o,'record_token_usage'), llm_model_context(model):
        client=factory.return_value.__enter__.return_value
        client.post.return_value=response(blocks=True)
        assert o._request_json('system','user','KODAME Project Overview',response_schema=schema)[0]=={'ok':True}
        payload=client.post.call_args.kwargs['json']
        assert payload['model']==model and payload['response_format']['json_schema']['strict']
        assert 'OUTPUT CONTRACT' in payload['messages'][0]['content']
        assert ('temperature' in payload)==(not model.startswith('openai/'))


@pytest.mark.parametrize('bad', ['{"ok":true,"ok":false}', '{"x":NaN}', '{"x":1e999}', '{"x":', '[]', '', None])
def test_never_salvages_invalid_json(bad):
    with pytest.raises((ValueError,TypeError)):
        parse_object(bad)


@pytest.mark.parametrize('error', ['json_schema is not supported','The compiled grammar is too large, which would cause performance issues.'])
def test_schema_capability_fallback_keeps_validation_and_model(error):
    schema={'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}
    rejected=httpx.Response(400,json={'error':{'message':error}},request=httpx.Request('POST','https://test.invalid'))
    with patch.object(o.httpx,'Client') as factory, patch.object(o,'OPENROUTER_API_KEY','test'), patch.object(o,'record_token_usage'):
        client=factory.return_value.__enter__.return_value
        client.post.side_effect=[rejected,response(content='{"ok":"true"}')]
        with pytest.raises(o.AnalysisError,match='schema mismatch'):
            o._request_json('s','u','test',response_schema=schema)
        assert client.post.call_count==2
        assert client.post.call_args.kwargs['json']['response_format']['type']=='json_object'


def test_transient_network_and_rate_limit_retry():
    with patch.object(o.httpx,'Client') as factory, patch.object(o,'OPENROUTER_API_KEY','test'), patch.object(o,'record_token_usage'), patch.object(o.time,'sleep'):
        client=factory.return_value.__enter__.return_value
        client.post.side_effect=[httpx.ConnectError('offline'),response(status=429),response()]
        assert o._request_json('s','u','test')[0]['ok']
        assert client.post.call_count==3


def valid_overview():
    return {**{f:{'text':'근거로 확인한 사업 정보','source_refs':['D001']} for f in overview.FIELDS},'conflicts':[]}


def test_overview_retries_broken_and_missing_output_then_accepts():
    good=valid_overview()
    with patch.object(overview,'_request_json',side_effect=[o.AnalysisError('JSON broken'),({'project_name':{}},'test'),(good,'test')]) as call:
        assert overview.request_overview('sources',{'D001'})==good
        assert call.call_count==3
        assert '직전 응답 검증 오류' in call.call_args.args[1]
        schema=call.call_args.kwargs['response_schema']
        assert set(schema['required'])==set(overview.FIELDS)|{'conflicts'}


def test_overview_rejects_unknown_refs_and_empty_field_without_saving():
    bad=valid_overview();bad['budget']['source_refs']=['D999']
    with patch.object(overview,'_request_json',return_value=(bad,'test')) as call:
        with pytest.raises(o.AnalysisError,match='3회'):
            overview.request_overview('sources',{'D001'})
        assert call.call_count==3


def test_terminal_billing_errors_are_not_format_retried():
    with patch.object(overview,'_request_json',side_effect=o.BillingError('no credits')) as call:
        with pytest.raises(o.BillingError): overview.request_overview('sources',{'D001'})
        assert call.call_count==1


def test_question_resume_skips_verified_question_but_revalidates_inputs():
    criterion=EVALUATION_CRITERIA['relevance']; cache={}; calls=[]
    pdm={'status':'unavailable','model':{}}
    def answer(system,prompt,title,**kwargs):
        data=json.loads(prompt.strip().split('\n{')[0]);qid=data['questions'][0]['question_id'];calls.append(qid)
        raw=dac.template({**criterion,'questions':[q for q in criterion['questions'] if q['id']==qid]})
        raw['question_assessments'][0]['finding']='제공된 문서에 실행 결과가 없어 해당 성과는 확인할 수 없습니다.'
        return raw,'test'
    def save(run,qid,digest,raw): cache[qid]={'digest':digest,'raw':copy.deepcopy(raw)}
    with patch.object(dac,'_request_json',side_effect=answer), patch.object(dac,'save_question',side_effect=save), patch.object(dac,'set_current_question'):
        dac.assess_criterion('relevance',criterion,[],{},pdm,run_id='first')
        assert len(calls)==len(criterion['questions'])
        failed=criterion['questions'][-1]['id'];del cache[failed];calls.clear()
        dac.assess_criterion('relevance',criterion,[],{},pdm,run_id='second',checkpoints=cache)
        assert calls==[failed]
        calls.clear()
        dac.assess_criterion('relevance',criterion,[],{'changed':True},pdm,run_id='third',checkpoints=cache)
        assert len(calls)==len(criterion['questions'])


def test_reference_aliases_map_only_citation_fields():
    raw={'finding':'E0001','evidence_ids':['E0001','unknown'],'table_row_id':'E0001','pdm_indicator_ids':['E0001']}
    mapped=dac._map_refs(raw,{'E0001':'Ecanonical'})
    assert mapped=={'finding':'E0001','evidence_ids':['Ecanonical','unknown'],'table_row_id':'Ecanonical','pdm_indicator_ids':['E0001']}
