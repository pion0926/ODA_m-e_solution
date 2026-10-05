"""Read-only UI review of the authorized user01 development workspace.

Uses a short-lived QA session, revoked in finally; no business writes or LLM calls.
Run only in compose project odame against the development services.
"""
import json
from pathlib import Path
from uuid import UUID

from fastapi import Request
from playwright.sync_api import sync_playwright, expect
from kodame_intake.auth import create_session, revoke_session
from kodame_intake.db import pool, connection, tenant_context
from kodame_intake.security import hash_session_token
from kodame_intake.settings import SESSION_COOKIE_NAME

BASE = 'http://kodame-redesign-web'
PROJECT = UUID('05460961-f12e-4fe7-ba6f-3e36e27bd23d')
OUT = Path('/review')
pool.open()
token = None
errors, statuses, denied_writes = [], {}, []
try:
    with tenant_context(system=True), connection() as conn, conn.transaction():
        row = conn.execute("SELECT a.id FROM accounts a JOIN project_members pm ON pm.account_id=a.id WHERE pm.project_id=%s AND a.email='user01@kodame.local' AND a.is_active=true",(PROJECT,)).fetchone()
        assert row, 'Authorized development user01 fixture not found'
    request = Request({'type':'http','headers':[(b'user-agent',b'ODAME QA read-only 20260919')],'client':('127.0.0.1',0)})
    token,_ = create_session(row['id'], request)
    with connection() as conn, conn.transaction():
        conn.execute("UPDATE auth_sessions SET selected_project_id=%s,expires_at=now()+interval '10 minutes' WHERE token_hash=%s",(PROJECT,hash_session_token(token)))
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.add_cookies([{'name':SESSION_COOKIE_NAME,'value':token,'url':BASE,'httpOnly':True,'sameSite':'Lax'}])
        def readonly(route):
            if route.request.method not in ('GET','HEAD'):
                denied_writes.append(route.request.url)
                route.abort()
            else: route.continue_()
        context.route('**/api/v2/**',readonly)
        page=context.new_page(); page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(BASE)
        expect(page.locator('#app')).to_be_visible()
        expect(page.locator('#statFiles')).to_have_text('52',timeout=20000)
        assert 'v2.2' in page.title()
        for endpoint in ('dashboard','intake/jobs?limit=200','pdm','project-overview','evaluations','project/lifecycle','report/sections','report/generation/latest','report/exports/latest','report/presentations/latest'):
            response=context.request.get(BASE+'/api/v2/'+endpoint)
            statuses[endpoint]=response.status
            assert response.status==200,(endpoint,response.status)
        for route in ('#/dashboard','#/evidence','#/evidence/pdm','#/evidence/dac','#/evidence/coverage','#/project/overview','#/project/indicators','#/project/gaps','#/eval/overview','#/eval/board','#/eval/results','#/eval/report'):
            page.evaluate('(route)=>{location.hash=route}',route)
            expect(page.locator('main .view:visible')).to_have_count(1)
            if route in ('#/dashboard','#/eval/board','#/eval/report'):
                page.screenshot(path=str(OUT/('live-'+route.split('/')[-1]+'.png')))
        page.evaluate("location.hash='#/evidence'")
        expect(page.locator('#cntAll')).to_have_text('52건')
        page.locator('#fileMore').click()
        expect(page.locator('#fileRows tr')).to_have_count(52)
        page.set_viewport_size({'width':390,'height':1000})
        assert page.locator('body').evaluate('(e)=>e.scrollWidth<=innerWidth+1')
        page.screenshot(path=str(OUT/'live-upload-390.png'))
        assert not errors,errors
        assert not denied_writes,denied_writes
        browser.close()
    result={'project_id':str(PROJECT),'version':'2.2','documents':52,'routes':12,'api_statuses':statuses,'page_errors':errors,'blocked_unexpected_writes':denied_writes,'business_writes':0,'external_ai_calls':0}
    (OUT/'live-readonly-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
finally:
    if token: revoke_session(token)
    pool.close()
