import { defineConfig } from '@playwright/test'
import base from './playwright.config'
export default defineConfig({
  ...base,
  retries: 0,
  workers: 1,
  reporter: [['list']],
  use: { ...base.use, baseURL: 'http://127.0.0.1:15198' },
  webServer: undefined,
})
