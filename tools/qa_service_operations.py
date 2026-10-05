"""Read-only HTTP operational checks in synthetic QA; never uses real accounts."""
import json, os
from pathlib import Path
import httpx

assert os.getenv('KODAME_QA')=='1'
assert 'qa-local-only@postgres' in os.environ['DATABASE_URL']
base='http://kodame-redesign-web:8080'
checks=[]
with httpx.Client(base_url=base,timeout=30) as client:
    health=client.get('/healthz')
    assert health.status_code==200
    denied=client.get('/api/v2/admin/runtime')
    assert denied.status_code==401 and len(denied.headers['x-request-id'])==32
    checks.append('anonymous diagnostics rejected and request ID returned')
    info=json.loads(Path('/qa/synthetic-accounts.json').read_text())
    assert client.post('/api/v2/auth/login',json=info['logins'][0]).status_code==200
    assert client.get('/api/v2/admin/runtime').status_code==403
    checks.append('project member cannot access global diagnostics')
    assert client.post('/api/v2/auth/login',json={'email':'admin','password':'qa-admin-local-only'}).status_code==200
    runtime=client.get('/api/v2/admin/runtime')
    assert runtime.status_code==200 and runtime.json()['prompt_versions']
    checks.append('administrator receives queue counts and prompt fingerprints')
    html=client.get('/').text
    assert 'K-ODAME v2.4' in html and '<style>' not in html
    for name in ('app-controller.js','app-shell.js','app-styles.css','assistant-avatar.png','service-auth.js'):
        response=client.get('/assets/'+name)
        assert response.status_code==200 and 'text/html' not in response.headers['content-type']
        assert 'no-store' in response.headers['cache-control']
    assert client.get('/assets/missing-qa-module.js').status_code==404
    checks.append('separate UI assets served with correct MIME, cache policy and missing-file 404')
result={'status':'passed','checks':checks}
Path('/qa/operations.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
