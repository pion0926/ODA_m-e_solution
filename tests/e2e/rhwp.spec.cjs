const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const fixture = fs.readFileSync(path.resolve(__dirname, '../../samples/5-1. 종료평가 결과보고서 placeholder.hwpx'));

async function rpc(page, method, params = {}) {
  return page.evaluate(({ method, params }) => new Promise((resolve, reject) => {
    const id = crypto.randomUUID();
    const timer = setTimeout(() => { window.removeEventListener('message', listener); reject(Error(method + ' timeout')); }, 30000);
    function listener(event) {
      if (event.origin !== location.origin || event.source !== window || event.data?.type !== 'rhwp-response' || event.data.id !== id) return;
      clearTimeout(timer); window.removeEventListener('message', listener);
      event.data.error ? reject(Error(event.data.error)) : resolve(event.data.result);
    }
    window.addEventListener('message', listener);
    window.postMessage({ type: 'rhwp-request', id, method, params }, location.origin);
  }), { method, params });
}

async function svgText(page, svg) {
  return page.evaluate(svg => [...new DOMParser().parseFromString(svg, 'image/svg+xml').querySelectorAll('text')].map(node => node.textContent).join(''), svg);
}

test('rHWP opens, renders and round-trips the report template offline', async ({ page }) => {
  test.setTimeout(120000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => new URL(route.request().url()).origin === 'http://127.0.0.1:8317' ? route.continue() : route.abort());
  await page.goto('/assets/rhwp/');
  expect(await rpc(page, 'ready')).toBe(true);
  await rpc(page, 'loadFile', { data: [...fixture], fileName: 'synthetic-template.hwpx', skipUnsavedGuard: true });
  const pages = await rpc(page, 'pageCount');
  expect(pages).toBeGreaterThan(1);
  const svg = await rpc(page, 'getPageSvg', { page: 0 });
  expect(svg).toContain('<svg');
  expect(await svgText(page, svg)).toMatch(/보고서|평가/);
  expect(Array.isArray(await rpc(page, 'getFieldList'))).toBe(true);
  expect(Array.isArray(await rpc(page, 'searchAllText', { query: '평가', includeCells: true }))).toBe(true);
  const exported = await rpc(page, 'exportHwpx');
  expect(exported.slice(0, 2)).toEqual([80, 75]);
  await rpc(page, 'loadFile', { data: exported, fileName: 'roundtrip.hwpx', skipUnsavedGuard: true });
  expect(await rpc(page, 'pageCount')).toBe(pages);
  expect(await svgText(page, await rpc(page, 'getPageSvg', { page: 0 }))).toMatch(/보고서|평가/);
  await expect(page.getByText('화면 스킨 선택', { exact: true })).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath('rhwp-first-page.png') });
  expect(errors).toEqual([]);
});

test('rHWP service save shortcut delegates to the host', async ({ page }) => {
  await page.route('**/*', route => new URL(route.request().url()).origin === 'http://127.0.0.1:8317' ? route.continue() : route.abort());
  // Force the real cold-load race: iframe load can precede dynamic Studio import.
  await page.route('**/assets/rhwp/assets/index-*.js', async route => {
    await new Promise(resolve => setTimeout(resolve, 1200));
    await route.continue();
  });
  await page.goto('/assets/rhwp/');
  await rpc(page, 'ready');
  await page.evaluate(() => {
    window.saveRequested = false;
    window.addEventListener('message', event => {
      if (event.origin === location.origin && event.data?.type === 'rhwp-safe-save-request') window.saveRequested = true;
    });
  });
  await page.keyboard.press('Control+s');
  await expect.poll(() => page.evaluate(() => window.saveRequested)).toBe(true);
});
