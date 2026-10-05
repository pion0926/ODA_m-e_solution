"""Read-only admin/user browser audit plus an actual download click."""
import json
from pathlib import Path
from uuid import UUID
from fastapi import Request
from playwright.sync_api import sync_playwright,expect
from kodame_intake.auth import create_session,revoke_session
from kodame_intake.db import pool,connection,tenant_context
from kodame_intake.security import hash_session_token
from kodame_intake.settings import SESSION_COOKIE_NAME

BASE='http://kodame-redesign-web';PROJECT=UUID('05460961-f12e-4fe7-ba6f-3e36e27bd23d')
OUT=Path('/app/data/qa/request12-20260919/browser');OUT.mkdir(parents=True,exist_ok=True)
pool.open();tokens=[];result={};errors=[]
try:
    with tenant_context(system=True),connection() as c:
        accounts=c.execute("SELECT id,email,is_admin FROM accounts WHERE is_active ORDER BY is_admin DESC").fetchall()
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        for account in accounts:
            admin=account['is_admin']
            if not admin and account['email']!='user01@kodame.local':continue
            token,_=create_session(account['id'],Request({'type':'http','headers':[(b'user-agent',b'ODAME request12 browser QA')],'client':('127.0.0.1',0)}));tokens.append(token)
            with connection() as c,c.transaction():
                c.execute("UPDATE auth_sessions SET selected_project_id=%s,expires_at=now()+interval '10 minutes' WHERE token_hash=%s",(None if admin else PROJECT,hash_session_token(token)))
            ctx=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
            ctx.add_cookies([{'name':SESSION_COOKIE_NAME,'value':token,'url':BASE,'httpOnly':True,'sameSite':'Lax'}])
            def readonly(route):
                if route.request.method not in ('GET','HEAD') and not route.request.url.endswith('/preview'):
                    errors.append('Unexpected write blocked: '+route.request.url);route.abort()
                else:route.continue_()
            ctx.route('**/api/v2/**',readonly)
            page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE)
            expect(page.locator('#app')).to_be_visible()
            if admin:
                page.evaluate("location.hash='#/admin/users'")
                expect(page.locator('#adminAccountRows')).to_contain_text('user01')
                page.locator('#adminAccountRows').get_by_text('user01',exact=True).click()
                expect(page.locator('#adminDetail')).to_contain_text('Paramedicine')
                for width in [1440,390]:
                    page.set_viewport_size({'width':width,'height':1000})
                    assert page.locator('body').evaluate('(e)=>e.scrollWidth<=innerWidth+1')
                    assert page.locator('#adminDetail').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
                    page.screenshot(path=str(OUT/f'admin-{width}.png'),full_page=True)
                result['admin']={'long_project_name_contained':True,'viewports':[1440,390]}
            else:
                expect(page.locator('#statFiles')).to_have_text('52')
                routes=['#/dashboard','#/evidence','#/evidence/pdm','#/evidence/dac','#/evidence/coverage','#/project/overview','#/project/indicators','#/project/gaps','#/eval/overview','#/eval/board','#/eval/results','#/eval/report']
                for route in routes:
                    page.evaluate('(r)=>location.hash=r',route)
                    expect(page.locator('main .view:visible')).to_have_count(1)
                expect(page.locator('#reportSubmissionKind')).to_be_visible()
                expect(page.locator('#reportSubmissionKind option')).to_have_count(6)
                page.locator('#seclist [data-id="feedback"]').click()
                expect(page.locator('#aiPrompt')).to_be_visible()
                expect(page.locator('#reportPreviewTitle')).to_contain_text('환류')
                page.screenshot(path=str(OUT/'report-ai-and-submissions.png'),full_page=True)
                page.locator('#reportSubmissionKind').select_option('grade-xlsx')
                with page.expect_download() as download:
                    page.locator('#reportSubmissionDownload').click()
                download.value.save_as(str(OUT/'ui-grade.xlsx'))
                expect(page.locator('#reportSubmissionStatus')).to_contain_text('다운로드 완료')
                page.set_viewport_size({'width':390,'height':1000})
                page.screenshot(path=str(OUT/'report-390.png'),full_page=True)
                overflow=page.evaluate("() => [...document.querySelectorAll('body *')].map(e=>({tag:e.tagName,id:e.id,cls:e.className,x:e.getBoundingClientRect().x,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width})).filter(e=>e.width>0 && e.right>innerWidth+2).slice(0,30)")
                (OUT/'overflow.json').write_text(json.dumps(overflow,ensure_ascii=False,indent=2),encoding='utf-8')
                assert page.locator('body').evaluate('(e)=>e.scrollWidth<=innerWidth+1')
                result['user']={'routes':len(routes),'files':52,'submission_options':6,'download_click':'passed','mobile_overflow':False}
            ctx.close()
        browser.close()
    result['page_errors']=errors
    (OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    assert not errors,errors
    print(json.dumps(result,ensure_ascii=False),flush=True)
finally:
    for token in tokens:revoke_session(token)
    pool.close()
