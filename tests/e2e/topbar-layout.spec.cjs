const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

// Use the shipped shell markup and stylesheet without authentication or APIs.
// A layout regression must not need real accounts, documents or external fonts.
const html = fs.readFileSync(path.resolve(__dirname, '../../frontend/index.html'), 'utf8');
const sidebar = html.match(/<aside id="gnb">[\s\S]*?<\/aside>/)[0];
const topbar = html.match(/<header class="topbar"[\s\S]*?<\/header>/)[0];
const fixture = `<!doctype html><html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/assets/app-styles.css"></head><body><div class="app">${sidebar}
<div class="shell">${topbar}<main><p>합성 성과지표 화면</p><div style="height:1000px"></div></main></div></div></body></html>`;

test('topbar keeps long project names and action buttons inside every viewport', async ({ page }) => {
  await page.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://127.0.0.1:8317' || url.pathname.startsWith('/api/')) return route.abort();
    if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: fixture });
    return route.continue();
  });
  await page.goto('/');
  await page.locator('#crumb').evaluate(el => { el.innerHTML = '사업 관리 <span class="sep">/</span><b>성과지표 모니터링</b>'; });
  await page.locator('#updTime').evaluate(el => { el.textContent = '업데이트 2026. 10. 8. 오전 8:25:59 (신규 평가 반영 완료)'; });
  const names = [
    '합성 농촌지역 보건기관 응급의료 대응역량 및 지역사회 기후재난 회복력 강화 사업 '.repeat(4),
    'InternationalCommunityHealthAndDisasterPreparednessCapacityBuildingProject'.repeat(5),
  ];
  for (const [nameIndex, name] of names.entries()) {
    await page.locator('#projChip .pn').evaluate((el, text) => { el.textContent = text; }, name);
    for (const width of [1440, 1032, 921, 800, 541, 390, 320]) {
      await test.step(`name ${nameIndex + 1}, ${width}px`, async () => {
        await page.setViewportSize({ width, height: 900 });
        const dimensions = await page.locator('#topbar').evaluate(top => {
          const bounds = top.getBoundingClientRect();
          const controls = Array.from(top.children).filter(el => el.getBoundingClientRect().width > 0)
            .map(el => { const r = el.getBoundingClientRect(); return { id: el.id, left: r.left, right: r.right, top: r.top, bottom: r.bottom }; });
          return { scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth,
            bounds: { left: bounds.left, right: bounds.right, top: bounds.top, bottom: bounds.bottom }, controls };
        });
        expect(dimensions.scrollWidth, 'No document horizontal scrollbar').toBeLessThanOrEqual(dimensions.clientWidth);
        for (const control of dimensions.controls) {
          expect(control.left, control.id).toBeGreaterThanOrEqual(dimensions.bounds.left);
          expect(control.right, control.id).toBeLessThanOrEqual(dimensions.bounds.right);
          expect(control.top, control.id).toBeGreaterThanOrEqual(dimensions.bounds.top);
          expect(control.bottom, control.id).toBeLessThanOrEqual(dimensions.bounds.bottom);
        }
        for (const id of ['projChip', 'trayBtn', 'uploadBtn']) {
          await expect(page.locator(`#${id}`)).toBeVisible();
          await page.locator(`#${id}`).click({ trial: true });
        }
        await page.locator('#projChip').focus();
        await page.keyboard.press('Tab');
        await expect(page.locator('#trayBtn')).toBeFocused();
        await page.keyboard.press('Tab');
        await expect(page.locator('#uploadBtn')).toBeFocused();
        await expect(page.locator('#uploadBtn')).toHaveText('증빙 업로드');
        if (width <= 920) {
          await page.keyboard.press('Tab');
          await expect(page.locator('#compactLogout')).toBeFocused();
          await page.locator('#compactLogout').click({ trial: true });
        }
      });
    }
  }
});
