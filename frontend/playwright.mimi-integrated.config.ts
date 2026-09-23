import { defineConfig, devices } from '@playwright/test'

/** B23 A2: the backend is started separately on an exact synthetic DB. */
export default defineConfig({
  testDir: './integrated',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'output/playwright/mimi-integrated' }]],
  use: {
    baseURL: 'http://127.0.0.1:8009',
    serviceWorkers: 'block',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } },
    },
    {
      name: 'mobile',
      use: {
        browserName: 'chromium',
        viewport: { width: 390, height: 844 },
        hasTouch: true,
        isMobile: true,
        userAgent: devices['iPhone 13'].userAgent,
        deviceScaleFactor: devices['iPhone 13'].deviceScaleFactor,
      },
    },
  ],
})
