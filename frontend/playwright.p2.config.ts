import { defineConfig } from '@playwright/test'
import config from './playwright.config'
export default defineConfig({ ...config, testMatch: ['mimi-p1.spec.ts', 'mimi-p2.spec.ts'], workers: 1,
  reporter: [['list'], ['json', { outputFile: 'test-results/p2-results.json' }]],
  outputDir: 'test-results/p2',
  use: { ...config.use, baseURL: 'http://127.0.0.1:4187' },
  webServer: { command: 'node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4187 --strictPort',
    port: 4187, reuseExistingServer: false, timeout: 30000 },
})
