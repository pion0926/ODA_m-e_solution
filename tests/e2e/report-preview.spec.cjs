const {test, expect} = require('@playwright/test');
const fs = require('node:fs');
const fixture = fs.readFileSync('samples/5-1. 종료평가 결과보고서 placeholder.hwpx');

test('latest section replaces a slow request and failed preview can retry', async ({page}) => {
  await page.route('**/assets/rhwp/?sectionPreview=1', route => route.fulfill({contentType:'text/html',body:`<script>addEventListener('message',e=>{if(e.data.type==='rhwp-request')parent.postMessage({type:'rhwp-response',id:e.data.id,result:e.data.method==='ready'?true:{pageCount:2}},location.origin)})</script>`}));
  await page.goto('/');
  await page.evaluate(() => { document.body.innerHTML = '<div id="reportWorkbench"></div><iframe id="reportSectionFrame"></iframe>' + ['reportPreviewStatus','reportPreviewEmpty','reportPreviewPages','reportPreviewZoom','reportPreviewNote','reportPreviewTitle'].map(id=>`<div id="${id}"></div>`).join('') + ['reportPreviewRefresh','reportPreviewExpand','reportZoomIn','reportZoomOut','reportZoomActual','reportZoomFit'].map(id=>`<button id="${id}">${id}</button>`).join(''); });
  await page.addScriptTag({url:'/assets/report-section-preview.js'});
  await page.evaluate(() => {
    window.aborted = false; window.failPreview = false;
    window.proof = ReportSectionPreview.create({request: (url, options) => {
      if(url.includes('/slow/')) return new Promise((resolve,reject) => options.signal.addEventListener('abort',()=>{window.aborted=true;reject(Error('aborted'));}));
      if(window.failPreview) return Promise.reject(Error('synthetic layout failure'));
      return Promise.resolve({part_id:'fast',hwpx_base64:btoa('test'),file_name:'test.hwpx',note:'검증'});
    }});
    proof.select('slow','old','이전 섹션');
  });
  await expect(page.locator('#reportPreviewStatus')).toContainText('조판 중');
  await expect(page.locator('#reportPreviewRefresh')).toBeEnabled();
  await page.evaluate(()=>proof.select('fast','new','현재 섹션'));
  await expect(page.locator('#reportPreviewStatus')).toHaveAttribute('data-state','ready');
  expect(await page.evaluate(()=>aborted)).toBe(true);
  await expect(page.locator('#reportPreviewTitle')).toHaveText('현재 섹션');
  await page.evaluate(()=>{window.failPreview=true;proof.refresh();});
  await expect(page.locator('#reportPreviewStatus')).toHaveAttribute('data-state','failed');
  await page.evaluate(()=>{window.failPreview=false;});
  await page.locator('#reportPreviewRefresh').click();
  await expect(page.locator('#reportPreviewStatus')).toHaveAttribute('data-state','ready');
});

test('full report proof has return and original HWPX download, no edit toolbar', async ({page}) => {
  const url='/api/v2/report/exports/11111111-1111-1111-1111-111111111111/download';
  await page.route('**/api/v2/report/exports/**/download',route=>route.fulfill({contentType:'application/octet-stream',body:fixture}));
  await page.goto('/assets/rhwp/?url='+encodeURIComponent(url));
  await expect(page.getByRole('link',{name:'← 보고서 작성으로 돌아가기'})).toHaveAttribute('href','/#/eval/report');
  await expect(page.getByRole('link',{name:'HWPX 내려받기'})).toHaveAttribute('href',url);
  await expect(page.locator('#menu-bar')).toBeHidden();
  await expect(page.locator('#icon-toolbar')).toBeHidden();
  await expect(page.getByText('생성된 보고서 · 읽기 전용')).toBeVisible();
  await expect(page.locator('.reader-page svg').first()).toBeVisible();
  const initialRendered = await page.locator('.reader-page svg').count();
  const pageCount = await page.locator('.reader-page').count();
  expect(initialRendered).toBeLessThan(pageCount);
  expect(Number((await page.locator('#reader-zoom').textContent()).replace('%',''))).toBeLessThanOrEqual(100);
  const text = page.locator('.reader-page svg text').filter({hasText:/[^\s]/}).first();
  const box = await text.boundingBox();
  expect(box).toBeTruthy();
  await page.mouse.move(box.x+1,box.y+box.height/2);
  await page.mouse.down();await page.mouse.move(box.x+Math.max(60,box.width)-1,box.y+box.height/2,{steps:15});await page.mouse.up();
  await expect.poll(()=>page.evaluate(()=>window.getSelection()?.toString())).not.toBe('');
  const before = await page.locator('.reader-page').first().textContent();
  await page.keyboard.press('Backspace');
  expect(await page.locator('.reader-page').first().textContent()).toBe(before);
  const number = page.getByRole('spinbutton');
  await number.fill('2');
  await page.getByRole('button',{name:'이동',exact:true}).click();
  await expect(page.locator('.reader-page').nth(1)).toHaveAttribute('aria-busy','false');
  const ids = await page.locator('.reader-page svg [id]').evaluateAll(nodes=>nodes.map(node=>node.id));
  expect(new Set(ids).size).toBe(ids.length);
  await expect.poll(() => page.locator('#reader-pages').evaluate(el => el.scrollTop)).toBeGreaterThan(100);
});

test('report reader shows a recoverable download failure', async ({page})=>{
  let failed=true;
  await page.route('**/api/v2/report/exports/**/download',route=>failed
    ?route.fulfill({status:503,body:'unavailable'})
    :route.fulfill({contentType:'application/octet-stream',body:fixture}));
  await page.goto('/assets/rhwp/?url='+encodeURIComponent('/api/v2/report/exports/11111111-1111-1111-1111-111111111111/download'));
  await expect(page.locator('#reader-status')).toContainText('파일 읽기 실패');
  failed=false;await page.getByRole('button',{name:'다시 시도',exact:true}).click();
  await expect(page.locator('.reader-page svg').first()).toBeVisible();
});


