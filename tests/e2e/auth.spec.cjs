const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  // No request can reach the real API or a third-party origin.
  await page.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://127.0.0.1:8317' || url.pathname.startsWith('/api/')) return route.abort();
    return route.continue();
  });
});

test('session check keeps login hidden until the server answers', async ({ page }) => {
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  await page.route('**/api/v2/auth/me', async route => {
    await pending;
    await route.fulfill({ status: 401, json: { detail: 'Not authenticated' } });
  });
  await page.goto('/');
  await expect(page.locator('#authStatus')).toBeVisible();
  await expect(page.locator('#authForm')).toBeHidden();
  finish();
  await expect(page.locator('#authForm')).toBeVisible();
  await expect(page.locator('#codeInput')).toBeFocused();
});

test('temporary session failure offers recovery instead of asking for credentials', async ({ page }) => {
  await page.route('**/api/v2/auth/me', route => route.fulfill({ status: 503, json: { detail: 'temporarily unavailable' } }));
  await page.goto('/');
  await expect(page.locator('#authRetry')).toBeVisible();
  await expect(page.locator('#authForm')).toBeHidden();
  await page.route('**/api/v2/auth/me', route => route.fulfill({ status: 401, json: {} }));
  await page.locator('#authRetry').click();
  await expect(page.locator('#authForm')).toBeVisible();
});

test('bootstrap failure gives a visible reload action', async ({ page }) => {
  await page.route('**/assets/app-shell.js*', route => route.abort());
  await page.goto('/');
  await expect(page.locator('#authRetry')).toBeVisible();
  await expect(page.locator('#authStatusMessage')).toContainText('화면을 불러오지 못했습니다');
});

test('rejected login shows the server error and re-enables submit', async ({ page }) => {
  await page.route('**/api/v2/auth/me', route => route.fulfill({ status: 401, json: {} }));
  await page.route('**/api/v2/auth/login', route => route.fulfill({ status: 401, json: { detail: '아이디 또는 비밀번호를 확인해 주세요.' } }));
  await page.goto('/');
  await page.getByLabel('아이디 또는 이메일', { exact: true }).fill('synthetic-user');
  await page.getByLabel('비밀번호', { exact: true }).fill('synthetic-password');
  await page.locator('#codeBtn').click();
  await expect(page.locator('#codeErr')).toContainText('아이디 또는 비밀번호');
  await expect(page.locator('#codeBtn')).toBeEnabled();
});
