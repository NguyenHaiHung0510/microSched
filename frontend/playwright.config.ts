import { defineConfig, devices } from '@playwright/test'

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
    baseURL: 'http://127.0.0.1:4173',
    serviceWorkers: 'block',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'mobile',
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
      },
    },
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } },
    },
  ],
  webServer: {
    command: 'npm run build && npm run preview -- --host 127.0.0.1',
    cwd: '.',
    port: 4173,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
