"""Capture the real production user UI for the customer manual; no content writes."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = 'https://app.kodame.kr'
OUT = Path('/app/data/qa/user-manual-20260920')
OUT.mkdir(parents=True, exist_ok=True)
credentials = json.loads(Path('/tmp/manual-capture-private.json').read_text(encoding='utf-8'))
manifest = []

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    context = browser.new_context(viewport={'width':1440,'height':1000}, device_scale_factor=2)
    page = context.new_page()
    page.goto(BASE, wait_until='networkidle')
    expect(page.locator('#codeBtn')).to_be_visible()
    page.locator('.gate-card').screenshot(path=str(OUT/'01-login.png'))
    page.locator('#codeInput').fill(credentials['username'])
    page.locator('#authPassword').fill(credentials['password'])
    page.locator('#codeBtn').click()
    try:
        expect(page.locator('#app')).to_be_visible(timeout=30000)
    except Exception:
        print('LOGIN ERROR:',page.locator('#codeErr').inner_text(),flush=True)
        raise
    expect(page.locator('#statFiles')).to_have_text('73',timeout=30000)

    def capture(name, selector=None, clip=None):
        page.evaluate('document.fonts.ready')
        page.screenshot(path=str(OUT/(name+'-full.png')))
        if selector:
            element=page.locator(selector)
            element.scroll_into_view_if_needed()
            box=element.bounding_box()
            if box['height'] > 740:
                page.screenshot(path=str(OUT/(name+'.png')),clip={
                    'x':box['x'],'y':max(0,box['y']),
                    'width':min(box['width'],1440-box['x']),
                    'height':min(740,1000-max(0,box['y']))})
            else:
                element.screenshot(path=str(OUT/(name+'.png')))
        elif clip:
            page.screenshot(path=str(OUT/(name+'.png')),clip=clip)
        else:
            page.screenshot(path=str(OUT/(name+'.png')))
        (OUT/(name+'.txt')).write_text(page.locator('body').inner_text(),encoding='utf-8')
        manifest.append({'name':name,'url':page.url,'selector':selector,'clip':clip,
            'buttons':page.locator('button:visible').evaluate_all('(es)=>es.map(e=>({id:e.id,text:e.innerText,disabled:e.disabled}))')})
        (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        print(name,flush=True)

    routes = [
        ('02-dashboard','#/dashboard'),('03-upload','#/evidence'),
        ('04-pdm-evidence','#/evidence/pdm'),('05-dac-evidence','#/evidence/dac'),
        ('06-coverage','#/evidence/coverage'),('07-overview','#/project/overview'),
        ('08-indicators','#/project/indicators'),('09-risks','#/project/gaps'),
        ('10-evaluation','#/eval/board'),('11-results','#/eval/results'),
        ('12-report','#/eval/report')]
    for name, route in routes:
        page.evaluate('(r)=>location.hash=r',route)
        expect(page.locator('main .view:visible')).to_have_count(1)
        page.wait_for_timeout(800)
        page.evaluate('window.scrollTo(0,0)')
        box=page.locator('main .view:visible').bounding_box()
        capture(name,clip={'x':box['x'],'y':max(0,box['y']),'width':box['width'],'height':min(650,1000-max(0,box['y']))})
        if name=='03-upload':
            capture('21-intake-complete',selector='#intakeHealth')
            page.locator('#fileSearch').fill('PDM')
            capture('23-additional-files',selector='#v-ev-manage > .panel:last-child')
            page.locator('#fileSearch').fill('')
        if name=='12-report':
            capture('22-hwpx-controls',selector='#v-eval-report > .repbar:first-child')
    page.evaluate("location.hash='#/evidence'")
    expect(page.locator('#uploadBtn')).to_be_visible()
    with page.expect_file_chooser() as chooser:
        page.locator('#uploadBtn').click()
    assert chooser.value.is_multiple()
    capture('13-file-selection',selector='#dropzone')
    page.evaluate("location.hash='#/eval/report'")
    expect(page.locator('#seclist')).to_be_visible()
    page.locator('#seclist [data-id="feedback"]').click()
    expect(page.locator('#reportPreviewTitle')).to_contain_text('환류')
    expect(page.locator('#reportPreviewStatus')).not_to_contain_text('조판 중',timeout=60000)
    page.wait_for_timeout(3000)
    box=page.locator('#repWrap').bounding_box()
    capture('14-report-feedback',clip={'x':box['x'],'y':max(0,box['y']),'width':box['width'],'height':min(690,1000-max(0,box['y']))})
    page.locator('#aiPrompt').fill('사실과 수치는 유지하고 중복 문장을 줄여 주세요.\n기관과 합의되지 않은 일정은 제안으로 구분해 주세요.')
    capture('15-ai-request',selector='.repai')
    if page.locator('#reportGenerationHistory').is_visible():
        if not page.locator('#reportGenerationHistory').get_attribute('open'):
            page.locator('#reportGenerationHistorySummary').click()
        capture('16-generation-history',selector='#reportGenerationHistory')
    page.locator('#aiPrompt').fill('')
    page.locator('#reportPreviewExpand').click()
    page.wait_for_timeout(500)
    capture('17-report-preview',selector='.report-preview-panel')
    page.locator('#reportPreviewExpand').click()
    page.locator('#presentationSlideCount').select_option('30')
    capture('18-presentation-controls',selector='#v-eval-report > .repbar:first-child')
    page.locator('#reportSubmissionKind').select_option('feedback-xlsx')
    capture('19-submission-controls',selector='.submission-bar')
    capture('24-presentation-complete',selector='#presentationProgress')
    page.evaluate("location.hash='#/dashboard'")
    expect(page.locator('#trayBtn')).to_be_visible()
    page.locator('#trayBtn').click()
    page.wait_for_timeout(400)
    capture('20-job-tray',selector='#tray')
    context.request.post(BASE+'/api/v2/auth/logout')
    context.close()
    browser.close()

(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
