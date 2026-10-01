import { defineConfig, devices } from '@playwright/test'

const uiPort = Number(process.env.MICROSCHED_E2E_PORT ?? 4173)

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'output/playwright/report' }],
  ],
  use: {
    baseURL: `http://127.0.0.1:${uiPort}`,
    serviceWorkers: 'block',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'mobile',
      testIgnore: 'outbox-core.browser.spec.ts',
      // Not `devices['iPhone 13']`: that preset defaults to the WebKit engine,
      // and the spec only asks for the 390x844 viewport + touch input, not
      // real Safari. Chromium keeps CI to one browser download (matches the
      // CI job below, which only installs chromium).
      use: {
        browserName: 'chromium',
        viewport: { width: 390, height: 844 },
        hasTouch: true,
        isMobile: true,
        userAgent: devices['iPhone 13'].userAgent,
        deviceScaleFactor: devices['iPhone 13'].deviceScaleFactor,
      },
    },
    {
      name: 'desktop',
      testIgnore: 'outbox-core.browser.spec.ts',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } },
    },
    {
      name: 'outbox-core',
      testMatch: 'outbox-core.browser.spec.ts',
      use: { browserName: 'chromium', baseURL: 'http://127.0.0.1:5172' },
    },
  ],
  webServer: [{
    command: `npm run build && npm run preview -- --host 127.0.0.1 --port ${uiPort} --strictPort`,
    cwd: '.',
    port: uiPort,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  }, {
    command: 'npm run dev -- --host 127.0.0.1 --port 5172',
    cwd: '.',
    port: 5172,
    reuseExistingServer: false,
    timeout: 60_000,
  }],
})
