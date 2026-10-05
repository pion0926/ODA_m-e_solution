"""A successful HTTP response can still contain a failed provider request."""
import copy
from unittest.mock import patch
import httpx
import pytest
from kodame_intake import ai_gateway as gateway


def response(status, body):
    return httpx.Response(status, json=body, request=httpx.Request('POST', 'https://test.invalid'))


@pytest.mark.parametrize('http_status', [200, 400])
def test_context_error_has_identical_recovery_class(http_status):
    body = {'error': {'code': 400, 'message': 'Provider returned error', 'metadata': {
        'raw': '{"error":{"message":"maximum context length exceeded"}}'}}}
    with patch.object(gateway.httpx, 'Client') as client, patch.object(gateway, 'OPENROUTER_API_KEY', 'test'):
        post = client.return_value.__enter__.return_value.post
        post.return_value = response(http_status, body)
        with pytest.raises(gateway.ContextLimitError, match='maximum context'):
            gateway._request_json('system', 'input', 'test')
        assert post.call_count == 1


@pytest.mark.parametrize('http_status', [200, 400])
def test_explicit_schema_incompatibility_falls_back_with_local_validation(http_status):
    seen = []
    replies = iter([response(http_status, {'error': {'code': 400, 'message': 'compiled grammar is too large'}}),
                    response(200, {'choices': [{'message': {'content': '{"ok":true}'}, 'finish_reason': 'stop'}]})])
    def post(*args, **kwargs):
        seen.append(copy.deepcopy(kwargs['json']))
        return next(replies)
    schema = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok'], 'additionalProperties': False}
    with patch.object(gateway.httpx, 'Client') as client, patch.object(gateway, 'OPENROUTER_API_KEY', 'test'), \
         patch.object(gateway, 'record_token_usage'):
        client.return_value.__enter__.return_value.post.side_effect = post
        assert gateway._request_json('system', 'input', 'test', response_schema=schema)[0] == {'ok': True}
    assert [p['response_format']['type'] for p in seen] == ['json_schema', 'json_object']
    assert seen[0]['model'] == seen[1]['model']
    assert 'JSON Schema' in seen[1]['messages'][0]['content']


def test_body_configuration_detail_preserved_without_credentials_or_retry():
    body = {'error': {'code': 401, 'message': 'Invalid key sk-secret-value Bearer hidden-credential'}}
    with patch.object(gateway.httpx, 'Client') as client, patch.object(gateway, 'OPENROUTER_API_KEY', 'test'):
        post = client.return_value.__enter__.return_value.post
        post.return_value = response(200, body)
        with pytest.raises(gateway.ConfigurationError) as caught:
            gateway._request_json('system', 'input', 'test')
        assert 'Invalid key' in str(caught.value)
        assert 'secret-value' not in str(caught.value) and 'hidden-credential' not in str(caught.value)
        assert post.call_count == 1


def test_body_billing_error_does_not_become_a_format_retry():
    with patch.object(gateway.httpx, 'Client') as client, patch.object(gateway, 'OPENROUTER_API_KEY', 'test'):
        post = client.return_value.__enter__.return_value.post
        post.return_value = response(200, {'error': {'code': 402, 'metadata': {'limit_source': 'openrouter_credits'}}})
        with pytest.raises(gateway.BillingError, match='크레딧'):
            gateway._request_json('system', 'input', 'test')
        assert post.call_count == 1
