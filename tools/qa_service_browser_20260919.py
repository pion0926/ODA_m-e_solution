"""Real browser flows, isolated service only; screenshots contain no passwords."""
import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from playwright.sync_api import sync_playwright, expect

BASE = 'http://odame-audit-web-20260919'
if urlparse(os.environ.get('ADMIN_DATABASE_URL', '')).path != '/kodame_service_isolated_test':
    raise RuntimeError('Disposable DB required')
OUT = Path('/review'); OUT.mkdir(exist_ok=True)
checks, errors = [], []
def passed(label):
    checks.append(label); print('PASS '+label, flush=True)
def login(page, email, password):
    page.goto(BASE)
    page.locator('#codeInput').fill(email)
    page.locator('#authPassword').fill(password)
    page.locator('#codeBtn').click()
    expect(page.locator('#app')).to_be_visible()

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    operator = browser.new_context(viewport={'width':1440,'height':1000})
    admin = operator.new_page(); admin.on('pageerror',lambda error:errors.append(str(error)))
    login(admin,'admin',os.environ['KODAME_BOOTSTRAP_PASSWORD'])
    admin.locator('#adminCreateProject').click()
    long_name = '서비스 점검 우즈베키스탄 응급구조학과 (Paramedicine) 구축 및 지역사회 CPCR (Cardio Pulmonary Cerebral Resuscitation), MCI (Mass Casualty Incident) 교육사업 ' + uuid.uuid4().hex[:5]
    admin.locator('#projectCreateName').fill(long_name)
    admin.locator('#projectCreateSubmit').click()
    expect(admin.locator('#serviceAccountDialog')).to_be_visible()
    username = 'browser_' + uuid.uuid4().hex[:7]
    admin.locator('[name=username]').fill(username)
    admin.locator('[name=display_name]').fill('서비스 검증 기관')
    admin.locator('#serviceAccountForm button[type=submit]').click()
    expect(admin.locator('#issuedPassword')).to_be_visible()
    password = admin.locator('#issuedPassword').inner_text()
    assert len(password)>=10
    admin.locator('#issuedAccountDone').click()
    expect(admin.locator('#adminDetail h2')).to_contain_text(username)
    account = next(row for row in operator.request.get(BASE+'/api/v2/admin/accounts').json()['accounts'] if row['username']==username)
    project = account['projects'][0]['id']
    passed('administrator creates project and connected account; one-time password is visible')
    for width in (1440,390):
        admin.set_viewport_size({'width':width,'height':1000})
        expect(admin.locator('#adminDetail')).to_be_visible()
        admin.locator('#adminDetail').screenshot(path=str(OUT/f'admin-detail-{width}.png'))
        overflow = admin.locator('#adminDetail').evaluate('(e)=>[e,...e.querySelectorAll("*")].filter(n=>n.clientWidth&&n.scrollWidth>n.clientWidth+1).map(n=>({tag:n.tagName,cls:n.className,w:n.clientWidth,scroll:n.scrollWidth,text:n.textContent.slice(0,80)}))')
        if overflow: print(json.dumps(overflow,ensure_ascii=False),flush=True)
        assert admin.locator('#adminDetail').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
        assert admin.locator('body').evaluate('(e)=>e.scrollWidth<=innerWidth+1')
        admin.locator('#adminDetail').screenshot(path=str(OUT/f'admin-detail-{width}.png'))
    passed('long project names fit administrator cards at 390 and 1440px')
    admin.set_viewport_size({'width':1440,'height':1000})
    second = operator.request.post(BASE+'/api/v2/admin/projects',data={'name':'탭 전환 검증 사업 '+uuid.uuid4().hex[:5], 'supported_locales':['ko'],'default_locale':'ko'}).json()['id']
    admin.locator('#adminRefresh').click()
    expect(admin.locator(f'[data-member-project="{second}"]')).to_be_visible()
    admin.locator(f'[data-member-project="{second}"]').check()
    with admin.expect_response(lambda response: response.url.endswith(f'/admin/accounts/{account["id"]}/projects') and response.request.method=='PUT') as save:
        admin.locator('[data-account-action=members]').click()
    assert save.value.status==200
    expect(admin.locator(f'[data-member-project="{second}"]')).to_be_checked()
    passed('administrator UI saves project assignments through the atomic endpoint')
    client = browser.new_context(viewport={'width':1440,'height':1000})
    user = client.new_page(); user.on('pageerror',lambda error:errors.append(str(error)))
    login(user,username,password)
    # First selected project is the one originally issued.
    assert client.request.get(BASE+'/api/v2/auth/me').json()['project']['id']==project
    user.evaluate("location.hash='#/evidence'")
    user.locator('#bulkFileInput').set_input_files([
        {'name':'사업 계획.txt','mimeType':'text/plain','buffer':'사업 계획 검증 자료'.encode()},
        {'name':'지원하지않음.exe','mimeType':'application/octet-stream','buffer':b'bad'},
        {'name':'빈파일.txt','mimeType':'text/plain','buffer':b''},
        {'name':'사업 결과.txt','mimeType':'text/plain','buffer':'후속 문서도 접수됨'.encode()},
    ])
    expect(user.locator('#uploadResult')).to_contain_text('새로 접수 2건',timeout=20000)
    expect(user.locator('#uploadResult')).to_contain_text('미접수 2건')
    expect(user.locator('#fileRows')).to_contain_text('사업 결과.txt')
    passed('mixed upload keeps successes, names failed files, and continues to later files')
    with psycopg.connect(os.environ['ADMIN_DATABASE_URL']) as conn:
        doc = conn.execute("UPDATE intake_documents SET status='failed',stage='failed',error_message='검증: 문서 형식을 확인하고 재시도해 주세요.' WHERE project_id=%s AND original_name='사업 계획.txt' RETURNING id",(project,)).fetchone()[0]
    expect(user.locator('[data-retry-document]')).to_be_visible(timeout=15000)
    for width in (1440,390):
        user.set_viewport_size({'width':width,'height':1000})
        user.screenshot(path=str(OUT/f'upload-recovery-{width}.png'),full_page=True)
        if not user.locator('body').evaluate('(e)=>e.scrollWidth<=innerWidth+1'):
            print(json.dumps(user.evaluate('()=>[...document.querySelectorAll("body *")].filter(e=>e.getClientRects().length && e.getBoundingClientRect().right>innerWidth+1 && getComputedStyle(e).position!=="fixed").slice(0,25).map(e=>({tag:e.tagName,cls:e.className,id:e.id,right:e.getBoundingClientRect().right,width:e.clientWidth}))'),ensure_ascii=False),flush=True)
        assert user.locator('body').evaluate('(e)=>e.scrollWidth<=innerWidth+1')
        user.screenshot(path=str(OUT/f'upload-recovery-{width}.png'),full_page=True)
    user.set_viewport_size({'width':1440,'height':1000})
    with user.expect_response(lambda response: response.url.endswith(f'/{doc}/retry')) as retry:
        user.locator('[data-retry-document]').click()
    assert retry.value.status==202
    passed('failed analysis is visible and retry works from the document list')
    routes = ['#/dashboard','#/evidence','#/evidence/pdm','#/evidence/dac','#/evidence/coverage','#/project/overview','#/project/indicators','#/project/gaps','#/eval/overview','#/eval/board','#/eval/results','#/eval/report']
    for route in routes:
        user.evaluate('(route)=>{location.hash=route}',route)
        user.wait_for_timeout(150)
        assert user.locator('#app').is_visible()
        assert user.locator('main .view:visible').count()==1,route
    passed('all 12 user menu routes render one visible workspace without JavaScript crashes')
    # Preserve an unsubmitted report request while another tab switches project.
    user.locator('#aiPrompt').fill('이 문구는 탭 전환 후에도 복사할 수 있어야 합니다.')
    other = client.new_page(); other.goto(BASE)
    expect(other.locator('#app')).to_be_visible()
    result = other.evaluate("async id=>await window.KODAME_REQUEST('/api/v2/account/projects/'+id+'/select',{method:'PUT'})",second)
    assert result['project']['id']==second
    rejected = user.evaluate("async()=>{try{await window.KODAME_REQUEST('/api/v2/report/generate-all',{method:'POST'});return null;}catch(e){return {code:e.code,status:e.status}}}")
    assert rejected=={'code':'workspace_changed','status':409}
    expect(user.locator('#workspaceChangedDialog')).to_be_visible()
    assert user.locator('#workspaceChangedDialog textarea').input_value().count('이 문구는 탭 전환 후에도 복사할 수 있어야 합니다.')==1
    user.screenshot(path=str(OUT/'cross-tab-protection.png'))
    passed('two real tabs: stale report action rejected and unsubmitted request remains copyable')
    user.locator('#workspaceChangedDialog button').click()
    expect(user.locator('#workspaceChangedDialog')).to_have_count(0)
    expect(user.locator('#app')).to_be_visible()
    user.evaluate("location.hash='#/evidence'")
    expect(user.locator('#cntAll')).to_have_text('0건')
    passed('workspace reload clears previous project documents')
    operator.request.put(BASE+f'/api/v2/admin/accounts/{account["id"]}/status',data={'is_active':False})
    expired = user.evaluate("async()=>{try{await window.KODAME_REQUEST('/api/v2/dashboard');return null;}catch(e){return e.status}}")
    assert expired==401
    expect(user.locator('#workspaceChangedDialog')).to_contain_text('다시 로그인')
    passed('administrator account suspension produces an actionable session-expired dialog')
    assert not errors, errors
    (OUT/'browser-result.json').write_text(json.dumps({'checks':checks,'page_errors':errors,'passed':len(checks)},ensure_ascii=False,indent=2),encoding='utf-8')
    browser.close()
print('BROWSER_SERVICE_AUDIT_PASS',len(checks),flush=True)
