import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  expect: { timeout: 10000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: process.env.BASE_URL || 'http://127.0.0.1:8080',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
  webServer: {
    command: 'python -m nas_md.cli web',
    port: 8080,
    reuseExistingServer: true,
    timeout: 20000,
    env: {
      WEB_PORT: '8080',
      WEB_HOST: '127.0.0.1',
      WEB_ROOT: './web',
      STORAGE_DIR: './storage-test-e2e',
    },
  },
});
