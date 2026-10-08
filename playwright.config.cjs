const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  timeout: 45000,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:8317',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    serviceWorkers: 'block',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'small-screen', use: { ...devices['Desktop Chrome'], viewport: { width: 800, height: 900 } } },
  ],
  webServer: {
    command: 'node tools/testing/static-server.cjs',
    url: 'http://127.0.0.1:8317',
    reuseExistingServer: false,
    timeout: 15000,
  },
});
