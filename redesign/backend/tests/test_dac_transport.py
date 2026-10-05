"""Provider billing behavior, without external requests or charges."""
from unittest.mock import patch
import httpx
import pytest
from kodame_intake import openrouter


def response(status, body, headers=None):
    return httpx.Response(status,json=body,headers=headers,request=httpx.Request('POST','https://test.invalid'))


def test_dac_output_limit_and_transient_budget_retry():
    budget=response(402,{'error':{'metadata':{'limit_source':'openrouter_in_flight_budget'}}},{'Retry-After':'4'})
    success=response(200,{'choices':[{'message':{'content':'{"ok":true}'},'finish_reason':'stop'}]})
    with patch.object(openrouter.httpx,'Client') as factory, patch.object(openrouter,'OPENROUTER_API_KEY','test'), \
         patch.object(openrouter,'record_token_usage'), patch.object(openrouter.time,'sleep') as sleep:
        client=factory.return_value.__enter__.return_value
        client.post.side_effect=[budget,success]
        assert openrouter._request_json('system','body','KODAME DAC Full Document Review')[0]=={'ok':True}
        assert client.post.call_count==2
        sleep.assert_called_once_with(4)
        assert client.post.call_args.kwargs['json']['max_tokens']==12000


def test_exhausted_credits_fail_without_model_format_retries():
    exhausted=response(402,{'error':{'metadata':{'limit_source':'openrouter_credits'}}})
    with patch.object(openrouter.httpx,'Client') as factory, patch.object(openrouter,'OPENROUTER_API_KEY','test'), \
         patch.object(openrouter.time,'sleep') as sleep:
        client=factory.return_value.__enter__.return_value
        client.post.return_value=exhausted
        with pytest.raises(openrouter.BillingError,match='크레딧을 충전'):
            openrouter._request_json('system','body','KODAME DAC Evidence Adjudication')
        assert client.post.call_count==1
        sleep.assert_not_called()
        assert client.post.call_args.kwargs['json']['max_tokens']==12000


def test_truncated_json_is_reported_as_output_limit():
    truncated=response(200,{'choices':[{'message':{'content':'{"incomplete":'},'finish_reason':'length'}]})
    with patch.object(openrouter.httpx,'Client') as factory, patch.object(openrouter,'OPENROUTER_API_KEY','test'), \
         patch.object(openrouter,'record_token_usage'):
        factory.return_value.__enter__.return_value.post.return_value=truncated
        with pytest.raises(openrouter.AnalysisError,match='출력 한도'):
            openrouter._request_json('system','body','KODAME DAC Evidence Adjudication')


def test_strict_schema_is_forwarded_only_to_supported_providers():
    success=response(200,{'choices':[{'message':{'content':'{}'}}]})
    schema={'type':'object','properties':{},'additionalProperties':False,'required':[]}
    with patch.object(openrouter.httpx,'Client') as factory, patch.object(openrouter,'OPENROUTER_API_KEY','test'), \
         patch.object(openrouter,'record_token_usage'):
        client=factory.return_value.__enter__.return_value
        client.post.return_value=success
        openrouter._request_json('system','body','KODAME DAC Evidence Adjudication',response_schema=schema)
        payload=client.post.call_args.kwargs['json']
        assert payload['response_format']['type']=='json_schema'
        assert payload['response_format']['json_schema']['schema']==schema
        assert payload['provider']['require_parameters'] is True


def test_schema_size_does_not_grow_with_evidence_enum_and_numeric_types_stay_numeric():
    from kodame_intake.dac_schema import question_schema
    small=question_schema('relevance-q1',['E1'])
    large=question_schema('relevance-q1',[f'E{i:024d}' for i in range(300)])
    assert small==large
    check=large['properties']['question_assessments']['items']['properties']['indicators']['items']
    quality=check['properties']['quality']['properties']
    assert quality['source_grade']=={'type':'integer','minimum':1,'maximum':4}
    assert 'enum' not in quality['source_grade']
    assert quality['directness']=={'type':'string','enum':['0','0.5','1']}


def test_request_configuration_errors_are_not_retried_as_generated_json_errors():
    rejected=response(400,{'error':{'message':'Provider returned error','metadata':{
        'raw':'{"error":{"message":"Invalid schema"}}'}}})
    with patch.object(openrouter.httpx,'Client') as factory, patch.object(openrouter,'OPENROUTER_API_KEY','test'):
        client=factory.return_value.__enter__.return_value
        client.post.return_value=rejected
        with pytest.raises(openrouter.ConfigurationError,match='Invalid schema'):
            openrouter._request_json('system','body','KODAME DAC Evidence Adjudication')
        assert client.post.call_count==1
