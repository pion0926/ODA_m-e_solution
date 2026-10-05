"""Readable close-ups from the unchanged production UI."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

out=Path('/app/data/qa/user-manual-20260920')
cred=json.loads(Path('/tmp/manual-capture-private.json').read_text())
with sync_playwright() as pw:
 b=pw.chromium.launch();c=b.new_context(viewport={'width':1440,'height':1000},device_scale_factor=2)
 p=c.new_page();p.goto('https://app.kodame.kr/',wait_until='networkidle')
 p.locator('#codeInput').fill(cred['username']);p.locator('#authPassword').fill(cred['password']);p.locator('#codeBtn').click()
 expect(p.locator('#app')).to_be_visible(timeout=30000)
 expect(p.locator('#statFiles')).to_have_text('73',timeout=30000)
 expect(p.locator('#statDac')).to_have_text('22/27',timeout=30000)
 def shot(name,selector,height=None):
  box=p.locator(selector).bounding_box()
  h=min(height or box['height'],1000-max(0,box['y']))
  p.screenshot(path=str(out/(name+'.png')),clip={'x':box['x'],'y':max(0,box['y']),'width':box['width'],'height':h})
  print(name,flush=True)
 for name,route,h in [
  ('03-upload','#/evidence',440),('06-coverage','#/evidence/coverage',390),
  ('07-overview','#/project/overview',500),('08-indicators','#/project/indicators',530),
  ('09-risks','#/project/gaps',385),('10-evaluation','#/eval/board',570),('11-results','#/eval/results',520)]:
  p.evaluate('(r)=>location.hash=r',route);p.wait_for_timeout(1600)
  p.evaluate('window.scrollTo(0,0)');shot(name,'main .view:visible',h)
 p.evaluate("location.hash='#/eval/report'")
 expect(p.locator('#seclist')).to_be_visible()
 p.locator('#seclist [data-id="feedback"]').click()
 expect(p.locator('#reportPreviewTitle')).to_contain_text('환류')
 expect(p.locator('#reportPreviewStatus')).to_contain_text('반영 완료',timeout=60000)
 p.evaluate('window.scrollTo(0,0)');shot('12-report','#v-eval-report',610)
 p.locator('#aiPrompt').fill('사실과 수치는 유지하고 중복 문장을 줄여 주세요.\n기관과 합의되지 않은 일정은 제안으로 구분해 주세요.')
 p.locator('.report-ai-label').scroll_into_view_if_needed()
 first=p.locator('.report-ai-label').bounding_box();last=p.locator('#aiGen').bounding_box()
 panel=p.locator('.repai').bounding_box()
 p.screenshot(path=str(out/'15-ai-request.png'),clip={'x':panel['x']+16,'y':first['y']-5,'width':panel['width']-32,'height':last['y']+last['height']-first['y']+10})
 history=p.locator('#reportGenerationHistory')
 if history.get_attribute('open') is None:p.locator('#reportGenerationHistorySummary').click()
 history.scroll_into_view_if_needed()
 first=history.bounding_box();last=p.locator('#reportGenerationMessage').bounding_box()
 p.screenshot(path=str(out/'16-generation-history.png'),clip={'x':first['x'],'y':first['y'],'width':first['width'],'height':last['y']+last['height']-first['y']+5})
 p.locator('#aiPrompt').fill('')
 p.locator('#reportPreviewExpand').click();p.wait_for_timeout(300)
 p.locator('.report-preview-panel').scroll_into_view_if_needed()
 shot('17-report-preview','.report-preview-panel',385)
 c.request.post('https://app.kodame.kr/api/v2/auth/logout');c.close();b.close()
