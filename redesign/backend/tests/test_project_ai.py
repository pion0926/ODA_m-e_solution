"""Project policy and provider routing regression tests; no paid API calls."""
import asyncio
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from kodame_intake import model_catalog, project_ai, main
from kodame_intake.api import middleware, auth_routes
from kodame_intake.llm_models import current_llm_model, llm_model_context, MODEL_OPTIONS

MODELS = ["google/gemini-3.8-flash", "openai/gpt-6-astra", "anthropic/claude-fable-5.1"]


def test_all_three_current_families_and_legacy_jobs_are_allowed():
    ids = {m['id'] for m in MODEL_OPTIONS}
    assert set(MODELS) <= ids
    assert {'google/gemini-3.5-flash-lite', 'anthropic/claude-opus-4.8'} <= ids


@pytest.mark.parametrize('value,expected', [('0.00001',10),('0',0),(None,None),('-1',None),('NaN',None),('Infinity',None)])
def test_pricing_per_token_to_per_million(value, expected):
    assert model_catalog.per_million(value) == expected


def test_live_catalog_marks_missing_model_unavailable_not_zero_price():
    data = {'data':[{'id':MODELS[0], 'pricing':{'prompt':'0.000001','completion':'0.000002'},
                     'supported_parameters':['response_format','temperature'], 'context_length':1000000}]}
    result = model_catalog.parse_catalog(data, datetime.now(timezone.utc).isoformat())
    assert result['models'][0]['input'] == 1
    missing = next(m for m in result['models'] if m['id'] == MODELS[1])
    assert not missing['available'] and missing['input'] is None


def test_catalog_outage_never_claims_live_prices_or_permits_new_assignment(monkeypatch):
    monkeypatch.setattr(model_catalog, '_cache', None)
    monkeypatch.setattr(model_catalog, '_attempt_at', 0)
    with patch.object(model_catalog.httpx, 'get', side_effect=httpx.ConnectError('offline')):
        first = model_catalog.get_model_catalog()
        second = model_catalog.get_model_catalog()
        assert first['price_status'] == second['price_status'] == 'stale'
        assert not first['can_assign']
        with pytest.raises(ValueError):
            model_catalog.require_available_model(MODELS[0])


def test_catalog_partial_response_retries_fresh_url_without_changing_model(monkeypatch):
    monkeypatch.setattr(model_catalog, '_cache', None)
    monkeypatch.setattr(model_catalog, '_attempt_at', 0)
    model = 'openai/gpt-5.6-luna'
    response = httpx.Response(200, request=httpx.Request('GET', model_catalog.CATALOG['source']),
                             json={'data': [{'id': model, 'supported_parameters': ['response_format']}]})
    with patch.object(model_catalog.httpx, 'get', side_effect=[httpx.ReadTimeout('partial body'), response]) as get:
        result = model_catalog.get_model_catalog()
        assert result['can_assign'] and result['price_status'] == 'live'
        assert model_catalog.require_available_model(model) == model
        assert get.call_count == 2
        assert get.call_args_list[0].args == get.call_args_list[1].args
        assert 'params' not in get.call_args_list[0].kwargs
        assert get.call_args_list[1].kwargs['params']['refresh']


def test_catalog_outage_recovery_is_not_cached_for_an_hour(monkeypatch):
    monkeypatch.setattr(model_catalog, '_cache', None)
    monkeypatch.setattr(model_catalog, '_attempt_at', 0)
    with patch.object(model_catalog.time, 'monotonic', return_value=100), \
         patch.object(model_catalog.httpx, 'get', side_effect=httpx.ConnectError('offline')) as get:
        model_catalog.get_model_catalog()
        model_catalog.get_model_catalog()
        assert get.call_count == 2
    response = httpx.Response(200, request=httpx.Request('GET', model_catalog.CATALOG['source']),
                             json={'data': [{'id': MODELS[0], 'supported_parameters': ['response_format']}]})
    with patch.object(model_catalog.time, 'monotonic', return_value=116), \
         patch.object(model_catalog.httpx, 'get', return_value=response) as get:
        assert model_catalog.get_model_catalog()['can_assign']
        assert get.call_count == 1


@pytest.mark.parametrize('model', MODELS)
def test_payload_preserves_policy_and_strips_unsupported_options(model):
    raw = {'model':model,'temperature':0.2,'top_p':0.8,'models':['other/model'],'route':'fallback','messages':[]}
    prepared = model_catalog.prepare_model_payload(raw)
    assert prepared['model'] == model and 'models' not in prepared and 'route' not in prepared
    assert ('temperature' in prepared) == model.startswith('google/')
    assert 'models' in raw  # no mutation of caller payload


def test_model_context_is_nested_and_async_task_isolated():
    original = current_llm_model()
    async def work(model):
        with llm_model_context(model):
            await asyncio.sleep(0)
            with llm_model_context():
                assert current_llm_model() == model
            return current_llm_model()
    async def run():
        return await asyncio.gather(*(work(model) for model in MODELS))
    assert asyncio.run(run()) == MODELS
    assert current_llm_model() == original


@pytest.mark.parametrize('model', MODELS)
def test_analysis_and_report_http_payloads_use_selected_project_model(model):
    from kodame_intake import openrouter, report_generator
    captured = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            captured.append(kwargs['json'])
            return httpx.Response(200, request=httpx.Request('POST',url), json={
                'model':model, 'choices':[{'message':{'content':'{"ok":true}'}}]})
    with llm_model_context(model), patch.object(httpx,'Client',Client), \
         patch.object(openrouter,'OPENROUTER_API_KEY','test-only'), \
         patch.object(openrouter,'record_token_usage'), patch.object(report_generator,'record_token_usage'):
        assert openrouter._request_json('system','test','qa')[0]['ok']
        assert report_generator._call_json('system','test','qa',0.1)['ok']
    assert len(captured) == 2 and all(p['model'] == model for p in captured)


def fake_connection(row):
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = row
    @contextmanager
    def connection():
        yield conn
    return conn, connection


def test_persisted_invalid_model_fails_closed(monkeypatch):
    conn, connection = fake_connection({'llm_model':'unknown/changed'})
    monkeypatch.setattr(project_ai,'connection',connection)
    with pytest.raises(HTTPException) as exc:
        project_ai.get_project_model('00000000-0000-0000-0000-000000000001')
    assert exc.value.status_code == 409


def test_assignment_optimistic_lock_and_audit(monkeypatch):
    row = {'status':'active','llm_model':MODELS[0],'ai_revision':2}
    conn, connection = fake_connection(row)
    monkeypatch.setattr(project_ai,'connection',connection)
    monkeypatch.setattr(project_ai,'require_available_model',lambda m:m)
    with pytest.raises(HTTPException) as exc:
        project_ai.update_project_model('project',MODELS[1],1,'admin')
    assert exc.value.status_code == 409
    assert not any(c.args[0].lstrip().startswith('UPDATE') for c in conn.execute.call_args_list)
    conn.execute.return_value.fetchone.side_effect = [row, {**row,'llm_model':MODELS[1],'ai_revision':3}]
    result = project_ai.update_project_model('project',MODELS[1],2,'admin')
    assert result['llm_model'] == MODELS[1]
    assert any('INSERT INTO project_ai_changes' in c.args[0] for c in conn.execute.call_args_list)


def test_background_export_and_presentation_capture_model_snapshot():
    seen = []
    with llm_model_context(MODELS[1]):
        main._run_background_for_account(lambda:seen.append(current_llm_model()),None,None,model=MODELS[0])
        assert current_llm_model() == MODELS[1]
    assert seen == [MODELS[0]]


@pytest.mark.parametrize('admin', [False, True])
def test_only_admin_may_assign_project_models(monkeypatch, admin):
    session = {'account_id':'00000000-0000-0000-0000-000000000001','project_id':None,'is_admin':admin}
    monkeypatch.setattr(middleware,'load_session',lambda token:session)
    monkeypatch.setattr(auth_routes,'update_project_model',lambda *args:{'llm_model':args[1]})
    client = TestClient(main.app)
    response = client.put('/api/v2/admin/projects/00000000-0000-0000-0000-000000000002/ai-model',
                          json={'llm_model':MODELS[0],'expected_revision':0})
    assert response.status_code == (200 if admin else 403)


def test_account_override_endpoint_cannot_bypass_admin_policy(monkeypatch):
    monkeypatch.setattr(middleware,'load_session',lambda token:{'account_id':'account','project_id':None,'is_admin':False})
    assert TestClient(main.app).put('/api/v2/account/settings',json={'llm_model':MODELS[1]}).status_code == 403


def test_every_ai_transport_uses_provider_compatibility_adapter():
    package = Path(main.__file__).parent
    for name in ('ai_gateway',
                 'theory_visual','presentation_exporter','presentation_reference_export'):
        text = (package / (name+'.py')).read_text(encoding='utf-8')
        assert 'json=prepare_model_payload(' in text, name
        assert 'OPENROUTER_PRESENTATION_MODEL' not in text, name
    # DAC now delegates transport to the shared OpenRouter adapter.
    assessor = (package / 'dac_assessor.py').read_text(encoding='utf-8')
    assert '_request_json(' in assessor
    assert 'client.post(' not in assessor
    overview = (package / 'project_overview.py').read_text(encoding='utf-8')
    assert '_request_json(' in overview
    assert 'client.post(' not in overview


def test_worker_followup_overview_and_parallel_translation_keep_context():
    from kodame_intake import worker
    from unittest.mock import MagicMock
    conn = MagicMock()
    from contextlib import nullcontext
    conn.transaction.return_value = nullcontext()
    with patch.object(worker,'_process') as process, patch.object(worker,'connection',return_value=nullcontext(conn)), patch.object(worker,'check'), patch('kodame_intake.project_ai.get_project_model',return_value=MODELS[0]):
        process.side_effect = lambda row: current_llm_model()
        with llm_model_context(MODELS[1]):
            worker.process({'analysis_model':MODELS[1],'project_id':'project','id':'test','attempts':1})
            assert current_llm_model() == MODELS[1]
        process.assert_called_once()
    text = (Path(main.__file__).parent/'localized_views.py').read_text(encoding='utf-8')
    assert 'copy_context().run, _translate_batch' in text


def test_model_change_invalidates_theory_visual_and_pdm_evidence_cache():
    from kodame_intake.theory_visual import theory_visual_input_digest
    digests = []
    for model in MODELS:
        with llm_model_context(model):
            digests.append(theory_visual_input_digest({'project':'test'}, {'theory':'same content'}, {}))
    assert len(set(digests)) == 3
    text = (Path(main.__file__).parent/'pdm_evidence.py').read_text(encoding='utf-8')
    assert 'MEASUREMENT_VERSION + current_llm_model()' in text
