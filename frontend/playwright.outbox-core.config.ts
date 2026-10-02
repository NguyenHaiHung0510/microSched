import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './e2e', testMatch: 'outbox-core.browser.spec.ts', workers: 1,
  reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:5172', serviceWorkers: 'block', browserName: 'chromium', trace: 'retain-on-failure' },
  outputDir: 'output/playwright/outbox-core',
  webServer: { command: 'npm run dev -- --host 127.0.0.1 --port 5172 --strictPort', port: 5172, reuseExistingServer: false, timeout: 60_000 },
})
