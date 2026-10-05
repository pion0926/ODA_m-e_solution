"""v2.2 behavioral regression against an explicitly disposable PostgreSQL DB."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from urllib.parse import urlparse
from unittest.mock import patch

if os.getenv('KODAME_ISOLATED_TEST') != '1' or urlparse(os.environ.get('ADMIN_DATABASE_URL', '')).path != '/kodame_service_isolated_test':
    raise RuntimeError('Requires the isolated disposable service test database')

from fastapi.testclient import TestClient
from kodame_intake.main import app
from kodame_intake.db import connection, tenant_context
from kodame_intake.settings import ORIGINALS_DIR

checks = []
def check(value, label):
    assert value, label
    checks.append(label)
    print('PASS ' + label, flush=True)

def req(client, method, path, status=200, **kwargs):
    response = client.request(method, '/api/v2' + path, **kwargs)
    assert response.status_code == status, (path, response.status_code, response.text)
    return response.json()

with TestClient(app) as admin:
    req(admin, 'POST', '/auth/login', json={'email':'admin', 'password':os.environ['KODAME_BOOTSTRAP_PASSWORD']})
    projects = [req(admin, 'POST', '/admin/projects', 201, json={'name':f'서비스 점검 {uuid.uuid4().hex[:6]}', 'supported_locales':['ko'], 'default_locale':'ko'}) for _ in range(3)]
    p, q, r = [item['id'] for item in projects]
    username = 'audit_' + uuid.uuid4().hex[:8]
    issued = req(admin, 'POST', '/admin/accounts', 201, json={'username':username, 'display_name':'검증 사용자', 'project_id':p})
    account = issued['id']
    user = TestClient(app)
    req(user, 'POST', '/auth/login', json={'email':username, 'password':issued['initial_password']})
    def members(desired, expected, status=200):
        return req(admin, 'PUT', f'/admin/accounts/{account}/projects', status, json={'project_ids':desired,'expected_project_ids':expected})
    members([q, str(uuid.uuid4())], [p], 422)
    check([row['id'] for row in req(user,'GET','/account/projects')['projects']] == [p], 'invalid batch rolls back all membership additions and removals')
    members([p,q], [p])
    members([r], [p], 409)
    check(set(row['id'] for row in req(user,'GET','/account/projects')['projects']) == {p,q}, 'stale administrator cannot overwrite newer assignments')
    # Two administrators saving the same original list: exactly one succeeds.
    def concurrent_save(desired):
        client = TestClient(app); client.cookies.update(admin.cookies)
        return client.put(f'/api/v2/admin/accounts/{account}/projects',json={'project_ids':desired,'expected_project_ids':[p,q]}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(concurrent_save, ([p], [p,q,r])))
    check(sorted(statuses) == [200,409], 'concurrent membership changes have exactly one winner')
    now = [row['id'] for row in req(user,'GET','/account/projects')['projects']]
    members([p,q], now)
    req(user,'PUT',f'/account/projects/{p}/select')
    headers = {'X-ODAME-Account':account,'X-ODAME-Project':p}
    req(user,'PUT',f'/account/projects/{q}/select',headers=headers)
    for path in ('/dashboard','/pdm','/report/sections','/evaluations'):
        check(req(user,'GET',path,409,headers=headers)['code']=='workspace_changed', 'old tab blocked: '+path)
    req(user,'POST','/intake/uploads',409,headers=headers,files={'files':('wrong-project.txt',b'blocked')})
    check(req(user,'GET','/intake/jobs')['total']==0, 'stale tab cannot write to newly selected project')
    req(user,'POST','/report/generate-all',409,headers=headers)
    req(admin,'GET','/admin/accounts',409,headers={'X-ODAME-Account':account})
    check(True,'stale identity blocks both user generation and operator data')
    req(user,'PUT',f'/account/projects/{p}/select')
    mixed = [('files',('good.txt',b'first')),('files',('bad.exe',b'bad')),('files',('empty.txt',b'')),('files',('large.txt',b'x'*33)),('files',('later.txt',b'later'))]
    with patch('kodame_intake.api.intake_routes.MAX_FILE_BYTES',16):
        batch = req(user,'POST','/intake/uploads',202,files=mixed,headers=headers)
    check(batch['count']==2 and [item['status'] for item in batch['rejected']]==[415,422,413], 'mixed batch reports accepted, unsupported, empty and oversize separately')
    duplicate = req(user,'POST','/intake/uploads',202,files={'files':('good.txt',b'first')})
    check(duplicate['accepted'][0]['deduplicated'] and req(user,'GET','/intake/jobs')['total']==2, 'retrying an accepted file never creates a duplicate')
    @contextmanager
    def broken_insert():
        with connection() as conn:
            class Proxy:
                def transaction(self): return conn.transaction()
                def execute(self,sql,params=None):
                    if 'INSERT INTO intake_documents' in sql: raise RuntimeError('injected database failure')
                    return conn.execute(sql,params)
            yield Proxy()
    with patch('kodame_intake.api.intake_routes.connection',broken_insert):
        failed = req(user,'POST','/intake/uploads',202,files={'files':('db-failure.txt',b'text')})
    check(failed['rejected_count']==1 and not list((ORIGINALS_DIR/p).rglob('db-failure.txt')), 'rolled-back upload reports error and removes unreferenced original')
    doc = batch['accepted'][0]['id']
    with tenant_context(p), connection() as conn, conn.transaction():
        conn.execute("UPDATE intake_documents SET status='failed',error_message='시험 분석 오류' WHERE id=%s",(doc,))
    life = req(user,'GET','/project/lifecycle')
    check(life['phase']=='documents_need_attention' and life['failed_document_count']==1 and not life['can_evaluate'], 'failed analysis explains the blocking recovery action')
    req(user,'POST',f'/intake/jobs/{doc}/retry',202)
    req(user,'POST',f'/intake/jobs/{doc}/retry',409)
    check(True,'failed document can retry once; queued work cannot be resubmitted')
    first = req(user,'GET','/intake/jobs?limit=1')
    req(user,'POST','/intake/uploads',202,files={'files':('new.txt',b'new')})
    second = req(user,'GET',f'/intake/jobs?limit=1&before={first["next_before"]}')
    check(first['items'][0]['id'] != second['items'][0]['id'] and second['next_before'] is None, 'cursor pagination stays stable when a new file arrives')
    members([q],[p,q])
    req(user,'GET','/dashboard',409,headers=headers)
    check(req(user,'GET','/auth/me')['project']['id']==q, 'removed membership immediately invalidates old page context')
    req(admin,'PUT',f'/admin/accounts/{account}/status',json={'is_active':False})
    req(user,'GET','/auth/me',401)
    members([], [q])
    members([p], [], 422)
    check(True,'suspended account loses sessions; removal remains possible; new assignment denied')
print(f'ISOLATED_SERVICE_UPGRADE_PASS {len(checks)} checks',flush=True)
