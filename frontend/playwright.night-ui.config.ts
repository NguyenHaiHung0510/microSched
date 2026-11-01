import { defineConfig } from '@playwright/test'
import base from './playwright.config'

// This lane owns its server/context; every Mimi response is synthetic.
export default defineConfig({
  ...base,
  testMatch: /mimi-(?:night-ui|p1|p2)\.spec\.ts|responsive-shell-096\.spec\.ts/,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  outputDir: 'output/playwright/night-ui',
  use: { ...base.use, baseURL: 'http://127.0.0.1:15210' },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 15210 --strictPort',
    port: 15210,
    reuseExistingServer: false,
  },
})
