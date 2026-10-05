"""Actual public HTTPS login and user/admin UI acceptance checks."""
import argparse,json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

parser=argparse.ArgumentParser();parser.add_argument('--final',action='store_true');args=parser.parse_args()
creds=json.loads(Path('/tmp/production-knut-private.json').read_text(encoding='utf-8'))
base='https://app.kodame.kr';out=Path('/app/data/qa/production-knut-20260920/browser');out.mkdir(parents=True,exist_ok=True)
result={};errors=[]
with sync_playwright() as p:
 browser=p.chromium.launch()
 for role,user,password in [('admin','admin',creds['admin_password']),('user',creds['username'],creds['password'])]:
  context=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
  page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
  page.goto(base,wait_until='domcontentloaded')
  page.locator('#codeInput').fill(user);page.locator('#authPassword').fill(password);page.locator('#codeBtn').click()
  expect(page.locator('#app')).to_be_visible(timeout=30000)
  cookies=context.cookies();assert any(c['name']=='kodame_production_session' and c['secure'] and c['httpOnly'] for c in cookies)
  if role=='admin':
   page.evaluate("location.hash='#/admin/users'");expect(page.locator('#adminAccountRows')).to_contain_text('knut')
   page.locator('#adminAccountRows').get_by_text('knut',exact=True).first.click();expect(page.locator('#adminDetail')).to_contain_text('knut')
   for width in [1440,390]:
    page.set_viewport_size({'width':width,'height':1000});assert page.locator('body').evaluate('(e)=>e.scrollWidth<=innerWidth+1')
    page.screenshot(path=str(out/f'admin-{width}.png'),full_page=True)
   result['admin']={'public_form_login':True,'project':'knut','responsive':True}
  else:
   expect(page.locator('#projChip .pn')).to_have_text('knut');expect(page.locator('#statFiles')).to_have_text('73')
   denied=context.request.get(base+'/api/v2/admin/accounts');assert denied.status==403
   routes=['#/dashboard','#/evidence','#/evidence/pdm','#/evidence/dac','#/evidence/coverage','#/project/overview','#/project/indicators','#/project/gaps','#/eval/overview','#/eval/board','#/eval/results','#/eval/report']
   for route in routes:
    page.evaluate('(r)=>location.hash=r',route);expect(page.locator('main .view:visible')).to_have_count(1)
   expect(page.locator('#reportSubmissionKind option')).to_have_count(6)
   page.screenshot(path=str(out/'report-1440.png'),full_page=True)
   if args.final:
    page.locator('#seclist [data-id="feedback"]').click();expect(page.locator('#aiPrompt')).to_be_visible()
    expect(page.locator('#reportPreviewTitle')).to_contain_text('환류')
    page.locator('#reportSubmissionKind').select_option('grade-xlsx')
    with page.expect_download() as dl:page.locator('#reportSubmissionDownload').click()
    dl.value.save_as(str(out/'knut-grade.xlsx'));expect(page.locator('#reportSubmissionStatus')).to_contain_text('다운로드 완료')
   page.set_viewport_size({'width':390,'height':1000});assert page.locator('body').evaluate('(e)=>e.scrollWidth<=innerWidth+1')
   page.screenshot(path=str(out/'report-390.png'),full_page=True)
   result['user']={'public_form_login':True,'admin_access_denied':True,'routes':12,'documents':73,'download_tested':args.final,'responsive':True}
  logout=context.request.post(base+'/api/v2/auth/logout');assert logout.status==204
  context.close()
 browser.close()
result['page_errors']=errors;(out/('final.json' if args.final else 'initial.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
assert not errors,errors
print(json.dumps(result,ensure_ascii=False),flush=True)
