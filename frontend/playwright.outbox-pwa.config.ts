import { defineConfig } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import path from 'node:path'

const receiptRoot = path.resolve(process.env.QA017_RECEIPT_DIR ?? '../output/outbox-pwa')
const buildSha = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()
const runTag = (process.env.QA017_RUN_TAG ?? `run-${Date.now()}-${process.pid}`).replace(/[^A-Za-z0-9_-]/g, '-')
const artifactDir = path.join(receiptRoot, 'artifacts')
const buildDir = path.join(artifactDir, 'builds', buildSha, 'dist')
const port = Number(process.env.QA017_PORT ?? 4174)
if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('Invalid QA017_PORT')
process.env.QA017_RECEIPT_DIR = receiptRoot
process.env.QA017_BUILD_SHA = buildSha
process.env.QA017_RUN_TAG = runTag

export default defineConfig({
  testDir: './e2e',
  testMatch: 'outbox-pwa.spec.ts',
  workers: 1,
  fullyParallel: false,
  retries: 0,
  maxFailures: 1,
  reporter: [['list'], ['json', { outputFile: path.join(artifactDir, 'reports', buildSha, `playwright-${runTag}.json`) }]],
  outputDir: path.join(artifactDir, 'playwright-output', buildSha, runTag),
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    browserName: 'chromium',
    serviceWorkers: 'allow',
    headless: process.env.QA017_HEADLESS === '1',
    trace: 'off',
    screenshot: 'only-on-failure',
    viewport: process.env.QA017_VIEWPORT === '390x844' ? { width: 390, height: 844 } : { width: 1280, height: 900 },
  },
  webServer: {
    command: 'node e2e/helpers/outbox-pwa-preview.mjs',
    cwd: '.',
    port,
    reuseExistingServer: false,
    timeout: 60_000,
    env: { QA017_BUILD_DIR: buildDir, QA017_PORT: String(port), QA017_RECEIPT_DIR: receiptRoot },
  },
})
