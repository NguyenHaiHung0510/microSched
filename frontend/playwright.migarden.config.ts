import { defineConfig } from '@playwright/test'

const baseURL = process.env.N01_BROWSER_ORIGIN ?? 'http://127.0.0.1:8871'
if (new URL(baseURL).hostname !== '127.0.0.1') throw new Error('N01 browser QA must use loopback')

export default defineConfig({
  testDir: './integrated',
  testMatch: 'migarden.spec.ts',
  timeout: 90_000,
  workers: 1,
  retries: 0,
  reporter: 'list',
  outputDir: './output/playwright/n01',
  use: { baseURL, browserName: 'chromium', serviceWorkers: 'block', trace: 'off' },
})
