"""Deployment smoke test: temporary session, GET-only business APIs and UI."""
import json
from fastapi import Request
import httpx
from playwright.sync_api import sync_playwright, expect
from kodame_intake.auth import create_session, revoke_session
from kodame_intake.db import pool, connection, tenant_context
from kodame_intake.security import hash_session_token
from kodame_intake.settings import SESSION_COOKIE_NAME, WORKER_CONCURRENCY

base = 'http://kodame-redesign-web'
pool.open(wait=True)
token = None
try:
    with tenant_context(system=True), connection() as conn:
        row = conn.execute('''SELECT a.id, pm.project_id FROM accounts a
            JOIN project_members pm ON pm.account_id=a.id
            WHERE a.is_active=true AND NOT a.is_admin
            ORDER BY (SELECT count(*) FROM intake_documents d WHERE d.project_id=pm.project_id) DESC
            LIMIT 1''').fetchone()
    assert row
    token, _ = create_session(row['id'], Request({'type':'http','headers':[], 'client':('127.0.0.1',0)}))
    with tenant_context(system=True), connection() as conn:
        conn.execute("UPDATE auth_sessions SET selected_project_id=%s,expires_at=now()+interval '5 minutes' WHERE token_hash=%s", (row['project_id'],hash_session_token(token)))
    statuses = {}
    with httpx.Client(base_url=base, cookies={SESSION_COOKIE_NAME:token}, timeout=45) as client:
        pending_pairs = None
        for endpoint in ('auth/me','intake/foundation','intake/jobs','pdm/analysis-plan','evaluations/analysis-plan','project/lifecycle','report/job-tray'):
            response = client.get('/api/v2/' + endpoint)
            statuses[endpoint] = response.status_code
            assert response.status_code == 200, (endpoint, response.status_code)
            if endpoint == 'intake/foundation':
                foundation_ready = response.json().get('ready')
            if endpoint == 'pdm/analysis-plan':
                pending_pairs=sum(len(i['document_ids']) for i in response.json()['indicators'])
    errors = []
    with sync_playwright() as engine:
        browser = engine.chromium.launch()
        context = browser.new_context(viewport={'width':1440,'height':1000})
        context.add_cookies([{'name':SESSION_COOKIE_NAME,'value':token,'url':base,'httpOnly':True,'sameSite':'Lax'}])
        context.route('**/*', lambda route: route.continue_() if route.request.method in ('GET','HEAD') else route.abort())
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(base, wait_until='networkidle')
        expect(page.locator('#app')).to_be_visible()
        page.evaluate("window.ServiceJobTray.update('qa-visibility',{name:'표시 검증',active:true,detail:'브라우저 표시 테스트'})")
        expect(page.locator('#tray')).to_be_visible()
        expect(page.locator('#tray')).to_have_class('tray on')
        expect(page.locator('#tray [data-close="tray"]')).to_be_hidden()
        page.evaluate("window.ServiceJobTray.update('qa-visibility',{name:'표시 검증',active:false,detail:'완료'})")
        expect(page.locator('#tray [data-close="tray"]')).to_be_visible()
        for route in ('#/evidence','#/project/indicators','#/eval/board','#/eval/report'):
            page.evaluate('(route)=>location.hash=route', route)
            expect(page.locator('main .view:visible')).to_have_count(1)
        browser.close()
    assert not errors, errors
    assert WORKER_CONCURRENCY == 4
    print(json.dumps({'api':statuses,'foundation_ready':foundation_ready,'pending_performance_pairs':pending_pairs,'automatic_tray_verified':True,'worker_concurrency':WORKER_CONCURRENCY,'ui_routes':4,'page_errors':errors}),flush=True)
finally:
    if token:
        revoke_session(token)
    pool.close()
