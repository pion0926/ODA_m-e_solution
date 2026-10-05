"""Destructive feature tests exclusively against a disposable database/storage."""
import os
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from unittest.mock import patch
import psycopg
from psycopg import sql

assert os.environ.get('KODAME_DELETION_TEST') == '1'
name = 'kodame_deletion_' + uuid.uuid4().hex[:12] + '_test'
admin_url = os.environ['ADMIN_DATABASE_URL']
with psycopg.connect(admin_url, autocommit=True) as conn:
    conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
for key in ('DATABASE_URL', 'ADMIN_DATABASE_URL'):
    os.environ[key] = urlunsplit(urlsplit(os.environ[key])._replace(path='/' + name))
os.environ['DATA_DIR'] = '/tmp/' + name
os.environ['THEORY_ARTIFACT_CACHE_DIR'] = '/tmp/' + name + '/theory_artifacts'
os.environ['KODAME_BOOTSTRAP_PASSWORD'] = 'IsolatedTestOnly2026!'
from fastapi.testclient import TestClient
from kodame_intake import main, project_deletion
from kodame_intake.db import connection, tenant_context, pool, open_pool

def req(client, method, path, status=200, **kwargs):
    response = client.request(method, '/api/v2/' + path, **kwargs)
    assert response.status_code == status, (path, response.status_code, response.text[:800])
    return response.json()

def file(relative):
    path = Path(os.environ['DATA_DIR']) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('isolated QA only')
    return path

try:
    with TestClient(main.app) as admin:
        req(admin, 'POST', 'auth/login', json={'email':'admin','password':os.environ['KODAME_BOOTSTRAP_PASSWORD']})
        projects = [req(admin, 'POST', 'admin/projects', 201, json={'name':f'Deletion QA {i}', 'supported_locales':['ko'],'default_locale':'ko'}) for i in range(2)]
        target, other = [p['id'] for p in projects]
        account = req(admin, 'POST', 'admin/accounts', 201, json={'username':'deleteqa','display_name':'Delete QA','project_id':target})
        req(admin, 'PUT', f"admin/projects/{other}/members/{account['id']}")
        user = TestClient(main.app)
        req(user, 'POST', 'auth/login', json={'email':'deleteqa','password':account['initial_password']})
        base = f'admin/projects/{target}'
        req(user, 'GET', base + '/deletion-preview', 403)
        doc = uuid.uuid4(); export = uuid.uuid4(); presentation = uuid.uuid4()
        paths = [file(f'originals/{target}/{doc}/original.txt'), file(f'extracted/{doc}.txt'),
                 file(f'report_exports/{export}.hwpx'), file(f'report_exports/{export}-theory.png'),
                 file(f'report_exports/diagnostics/{export}/candidate.hwpx'),
                 file(f'presentation_exports/{presentation}.pptx'), file(f'presentation_exports/{presentation}.json'),
                 file(f'presentation_exports/checkpoints/{target}/slides.json'), file(f'theory_artifacts/{target}/digest/theory.png')]
        survivor = file(f'originals/{other}/keep.txt')
        with tenant_context(system=True), connection() as conn:
            conn.execute('UPDATE projects SET owner_account_id=%s WHERE id=%s', (account['id'],other))
            conn.execute('''INSERT INTO intake_documents(id,project_id,original_name,stored_path,extracted_path,extension,size_bytes,sha256,status)
                VALUES (%s,%s,'original.txt',%s,%s,'.txt',16,%s,'completed')''', (doc,target,str(paths[0]),str(paths[1]),'a'*64))
            conn.execute("INSERT INTO report_exports(id,project_id,status,output_path) VALUES (%s,%s,'completed',%s)", (export,target,str(paths[2])))
            conn.execute("INSERT INTO presentation_exports(id,project_id,status,output_path,model) VALUES (%s,%s,'completed',%s,'test')", (presentation,target,str(paths[5])))
        preview = req(admin, 'GET', base + '/deletion-preview')
        assert preview['accounts'][0]['other_projects'] == [projects[1]['name']]
        payload = {'name':preview['name'],'revision':preview['revision'],'confirmed':True}
        req(user, 'DELETE', base, 403, json=payload)
        req(admin, 'DELETE', base, 409, json={**payload,'confirmed':False})
        req(admin, 'DELETE', base, 409, json={**payload,'name':'wrong'})
        req(admin, 'DELETE', base, 409, json={**payload,'revision':'0'*64})
        with tenant_context(system=True), connection() as conn:
            conn.execute("UPDATE intake_documents SET status='processing' WHERE id=%s", (doc,))
        req(admin, 'DELETE', base, 409, json=payload)
        with tenant_context(system=True), connection() as conn:
            conn.execute("UPDATE intake_documents SET status='waiting_llm' WHERE id=%s", (doc,))
            shared_doc = uuid.uuid4()
            conn.execute('''INSERT INTO intake_documents(id,project_id,original_name,stored_path,extension,size_bytes,sha256,status)
                VALUES (%s,%s,'shared.txt',%s,'.txt',16,%s,'completed')''', (shared_doc,other,str(paths[0]),'b'*64))
        req(admin, 'DELETE', base, 409, json=payload)
        with tenant_context(system=True), connection() as conn:
            conn.execute('DELETE FROM intake_documents WHERE id=%s', (shared_doc,))
        assert all(p.exists() for p in paths)
        print('PASS admin authorization, exact name/final confirmation, stale scope, active job rejection', flush=True)

        # Real browser dialog: cancel, name gate, second confirmation, real delete API.
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
            page = browser.new_page()
            page.set_content('<button id="open">Delete</button><div id="notice"></div>')
            def bridge(path, options):
                import json
                response = admin.request(options.get('method','GET'), path, json=json.loads(options['body']) if options.get('body') else None)
                return {'status':response.status_code,'data':response.json()}
            page.expose_function('apiBridge', bridge)
            page.add_script_tag(path='/workspace/assets/service-admin-ui.js')
            page.evaluate('''() => { window.ui = ServiceAdminUI.create({
                request:async (path,options={})=>{const r=await apiBridge(path,options);if(r.status>=400)throw Error(r.data.detail);return r.data;},
                escapeHtml:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),
                refresh:async()=>{},accounts:()=>[],projects:()=>[],selected:()=>null,
                notify:s=>document.querySelector('#notice').textContent=s}); }''')
            page.evaluate('(id)=>ui.deleteProject(id)', target)
            expect(page.locator('#projectDeleteDialog')).to_be_visible()
            expect(page.locator('[data-delete-submit]')).to_be_disabled()
            page.locator('[data-delete-cancel]').click()
            req(admin, 'GET', base + '/deletion-preview')
            page.evaluate('(id)=>ui.deleteProject(id)', target)
            page.locator('input[name=projectName]').fill(preview['name'])
            page.locator('[data-delete-submit]').click()
            expect(page.locator('[data-delete-state]')).to_contain_text('정말 삭제하시겠습니까?')
            req(admin, 'GET', base + '/deletion-preview')
            # Simulate transient filesystem error: DB commits but manifest survives.
            with patch.object(project_deletion, 'cleanup_files'):
                page.locator('[data-delete-submit]').click()
                expect(page.locator('#notice')).to_contain_text('재시도')
            browser.close()
        with tenant_context(system=True), connection() as conn:
            assert not conn.execute('SELECT 1 FROM accounts WHERE id=%s',(account['id'],)).fetchone()
            assert not conn.execute('SELECT 1 FROM projects WHERE id=%s',(target,)).fetchone()
            assert conn.execute('SELECT 1 FROM projects p JOIN accounts a ON a.id=p.owner_account_id WHERE p.id=%s AND a.is_admin',(other,)).fetchone()
            assert not conn.execute('SELECT 1 FROM intake_documents WHERE id=%s',(doc,)).fetchone()
            assert not conn.execute('SELECT 1 FROM report_exports WHERE id=%s',(export,)).fetchone()
            assert not conn.execute('SELECT 1 FROM presentation_exports WHERE id=%s',(presentation,)).fetchone()
            assert not conn.execute('SELECT 1 FROM auth_sessions WHERE account_id=%s',(account['id'],)).fetchone()
        project_deletion.cleanup_files()
        assert all(not p.exists() for p in paths)
        assert survivor.exists()
        req(user,'GET','auth/me',401)
        req(admin,'GET',base+'/deletion-preview',404)
        req(admin,'GET','auth/me')
        print('PASS browser cancel/name/second confirmation; cascaded DB/account/session deletion; durable file cleanup; other project preserved', flush=True)
        with tenant_context(system=True), connection() as conn:
            bootstrap = conn.execute('SELECT id FROM projects WHERE is_bootstrap').fetchone()['id']
        preview = req(admin,'GET',f'admin/projects/{bootstrap}/deletion-preview')
        req(admin,'DELETE',f'admin/projects/{bootstrap}',json={'name':preview['name'],'revision':preview['revision'],'confirmed':True})
        open_pool()
        with tenant_context(system=True), connection() as conn:
            assert not conn.execute('SELECT 1 FROM projects WHERE is_bootstrap').fetchone()
        print('PASS deleted bootstrap project stays deleted after startup migration', flush=True)
finally:
    pool.close()
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
