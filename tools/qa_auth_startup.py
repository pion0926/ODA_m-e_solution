"""Production read-only auth UI scenarios; no AI calls or user data changes."""
import asyncio
import json
from fastapi import Request
from playwright.async_api import async_playwright, expect
from kodame_intake.auth import create_session, revoke_session
from kodame_intake.db import pool,connection,tenant_context
from kodame_intake.security import hash_session_token
from kodame_intake.settings import SESSION_COOKIE_NAME

BASE='http://kodame-redesign-web'

async def check(token):
    async with async_playwright() as engine:
        browser=await engine.chromium.launch()
        context=await browser.new_context()
        await context.add_cookies([{'name':SESSION_COOKIE_NAME,'value':token,'url':BASE,'httpOnly':True,'sameSite':'Lax'}])
        await context.route('**/*',lambda route:route.continue_() if route.request.method in ('GET','HEAD') else route.abort())
        page=await context.new_page()
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        release=asyncio.Event()
        async def delayed(route):
            await release.wait()
            await route.continue_()
        await page.route('**/api/v2/auth/me',delayed)
        await page.goto(BASE,wait_until='domcontentloaded')
        await expect(page.locator('#authStatus')).to_be_visible()
        await expect(page.locator('#authForm')).to_be_hidden()
        await expect(page.locator('#app')).to_be_hidden()
        release.set()
        await expect(page.locator('#app')).to_be_visible()
        for _ in range(2):
            release.clear()
            await page.reload(wait_until='domcontentloaded')
            await expect(page.locator('#authStatus')).to_be_visible()
            await expect(page.locator('#authForm')).to_be_hidden()
            release.set()
            await expect(page.locator('#app')).to_be_visible()
        await page.unroute('**/api/v2/auth/me',delayed)
        await page.route('**/api/v2/auth/me',lambda route:route.fulfill(status=503,json={'detail':'temporary outage'}))
        await page.reload(wait_until='domcontentloaded')
        await expect(page.locator('#authRetry')).to_be_visible()
        await expect(page.locator('#authForm')).to_be_hidden()
        await expect(page.locator('#app')).to_be_hidden()
        await page.unroute('**/api/v2/auth/me')
        await page.locator('#authRetry').click()
        await expect(page.locator('#app')).to_be_visible()
        await context.close()
        anonymous=await browser.new_context()
        login=await anonymous.new_page()
        await login.goto(BASE,wait_until='domcontentloaded')
        await expect(login.locator('#authForm')).to_be_visible()
        await expect(login.locator('#authStatus')).to_be_hidden()
        await expect(login.locator('#app')).to_be_hidden()
        # A blocked/missing module must offer reload, not a credentials form.
        await login.route('**/assets/service-auth.js*',lambda route:route.abort())
        await login.reload(wait_until='domcontentloaded')
        await expect(login.locator('#authRetry')).to_be_visible()
        await expect(login.locator('#authForm')).to_be_hidden()
        await browser.close()
        assert not errors,errors
        print(json.dumps({'session_restoration':True,'reloads':2,'no_login_during_check':True,
            'network_error_retry':True,'anonymous_login':True,'module_failure_no_login':True,'page_errors':errors}))

pool.open(wait=True)
token=None
try:
    with tenant_context(system=True),connection() as conn:
        row=conn.execute("SELECT a.id,pm.project_id FROM accounts a JOIN project_members pm ON pm.account_id=a.id WHERE a.is_active AND NOT a.is_admin LIMIT 1").fetchone()
    token,_=create_session(row['id'],Request({'type':'http','headers':[],'client':('127.0.0.1',0)}))
    with tenant_context(system=True),connection() as conn:
        conn.execute("UPDATE auth_sessions SET selected_project_id=%s,expires_at=now()+interval '5 minutes' WHERE token_hash=%s",(row['project_id'],hash_session_token(token)))
    asyncio.run(check(token))
finally:
    if token:revoke_session(token)
    pool.close()
