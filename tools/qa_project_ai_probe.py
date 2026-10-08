"""Development-only integration probe. Synthetic content; no existing drafts changed.

Run inside the development API container after deployment. Creates two empty QA
projects and one temporary QA user (disabled at the end). Never logs credentials.
Six small paid calls exercise the same analysis/report clients used by the app.
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx

from kodame_intake.db import pool, tenant_context
from kodame_intake.llm_models import llm_model_context
from kodame_intake.project_ai import get_project_model
from kodame_intake.openrouter import _request_json
from kodame_intake.report_generator import _call_json


def run():
    if os.environ.get('SESSION_COOKIE_NAME') != 'kodame_session':
        raise RuntimeError('Only the development environment is allowed.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    result = {'created_at':stamp,'scope':'development only','projects':[], 'checks':[], 'calls':[]}
    pool.open(wait=True)
    admin = httpx.Client(base_url='http://127.0.0.1:8100',timeout=30,trust_env=False)
    user = httpx.Client(base_url='http://127.0.0.1:8100',timeout=30,trust_env=False)
    account = None
    try:
        login = admin.post('/api/v2/auth/login',json={
            'email':os.getenv('KODAME_BOOTSTRAP_EMAIL','admin@kodame.local'),
            'password':os.getenv('KODAME_BOOTSTRAP_PASSWORD','admin')})
        login.raise_for_status()
        for suffix in ('A','B'):
            response = admin.post('/api/v2/admin/projects',json={
                'name':f'[QA] 프로젝트 AI 배정 {stamp} {suffix}', 'supported_locales':['ko'],
                'default_locale':'ko','account_ids':[]})
            response.raise_for_status(); result['projects'].append(response.json()['id'])
        project_a, project_b = result['projects']
        response = admin.post('/api/v2/admin/accounts',json={
            'username':'aiqa-'+stamp, 'display_name':'AI 모델 배정 검증용', 'project_id':project_a})
        response.raise_for_status(); account = response.json()
        response = user.post('/api/v2/auth/login',json={'email':account['username'],'password':account['initial_password']})
        response.raise_for_status()
        assert user.get('/api/v2/admin/ai-models').status_code == 403
        assert user.put('/api/v2/account/settings',json={'llm_model':'openai/gpt-6-astra'}).status_code == 403
        result['checks'].append('ordinary user cannot override project policy or access admin catalog')
        projects = admin.get('/api/v2/admin/projects').json()['projects']
        before_b = next(p for p in projects if p['id'] == project_b)['llm_model']
        revision = next(p for p in projects if p['id'] == project_a)['ai_revision']
        for model in ('google/gemini-3.8-flash','openai/gpt-6-astra','anthropic/claude-fable-5.1'):
            response = admin.put(f'/api/v2/admin/projects/{project_a}/ai-model',json={
                'llm_model':model,'expected_revision':revision})
            response.raise_for_status(); saved = response.json()
            assert user.get('/api/v2/account/settings').json()['llm_model'] == model
            stale = admin.put(f'/api/v2/admin/projects/{project_a}/ai-model',json={
                'llm_model':model,'expected_revision':revision})
            assert stale.status_code == 409
            revision = saved['ai_revision']
            rows = admin.get('/api/v2/admin/projects').json()['projects']
            assert next(p for p in rows if p['id'] == project_b)['llm_model'] == before_b
            result['checks'].append(f'{model}: persistence, effective user setting, stale-update rejection, project isolation')
            with tenant_context(project_a,account_id=account['id']), llm_model_context(get_project_model(project_a)):
                for stage in ('analysis','report'):
                    observed = []
                    original_post = httpx.Client.post
                    def observe(client,url,**kwargs):
                        response = original_post(client,url,**kwargs)
                        if '/chat/completions' in str(url):
                            body = response.json()
                            observed.append({'requested':kwargs['json']['model'], 'returned':body.get('model'),
                                             'status':response.status_code,'usage':body.get('usage')})
                        return response
                    started = time.monotonic()
                    system = 'Return a JSON object only. This is a synthetic API routing check, not a real project.'
                    prompt = 'Synthetic project: planned trainees 10; completed trainees 8. Return {"achievement_percent":80,"summary":"목표 대비 80% 달성함."}. Do not add other keys.'
                    try:
                        with patch.object(httpx.Client,'post',observe):
                            body = _request_json(system,prompt,'KODAME development routing QA')[0] if stage == 'analysis' else _call_json(system,prompt,'KODAME development report QA',0.1)
                        passed = body.get('achievement_percent') == 80 and all(o['requested'] == model and o['returned'] == model and o['status'] == 200 for o in observed)
                        result['calls'].append({'stage':stage,'model':model,'passed':passed,
                                                'seconds':round(time.monotonic()-started,2),'observed':observed,'response':body})
                        print(json.dumps({'stage':stage,'model':model,'passed':passed},ensure_ascii=False),flush=True)
                    except Exception as exc:
                        result['calls'].append({'stage':stage,'model':model,'passed':False,
                                                'observed':observed,'error':str(exc)[:300]})
                        print(json.dumps({'stage':stage,'model':model,'passed':False,'error_type':type(exc).__name__}),flush=True)
        # Leave the empty QA project on the low-cost current Flash model.
        response = admin.put(f'/api/v2/admin/projects/{project_a}/ai-model',json={
            'llm_model':'google/gemini-3.8-flash','expected_revision':revision})
        response.raise_for_status()
        result['passed'] = len(result['calls']) == 6 and all(c['passed'] for c in result['calls'])
    finally:
        if account:
            response = admin.put(f"/api/v2/admin/accounts/{account['id']}/status",json={'is_active':False})
            result['qa_user_disabled'] = response.status_code == 200
            result['qa_username'] = account['username']
        admin.post('/api/v2/auth/logout'); user.close(); admin.close(); pool.close()
        destination = Path('/tmp/project-ai-probe.json')
        destination.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    if not result.get('passed'):
        raise SystemExit(1)


if __name__ == '__main__':
    run()
