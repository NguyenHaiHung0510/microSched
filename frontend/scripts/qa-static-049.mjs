import assert from 'node:assert/strict'
import { chromium } from '@playwright/test'

const baseURL = process.env.HOMEPAGE_QA_URL || 'http://127.0.0.1:8049'
assert(['127.0.0.1', 'localhost'].includes(new URL(baseURL).hostname))
const browser = await chromium.launch({ headless: true })
const deadline = setTimeout(() => {
  console.error('QA deadline exceeded')
  void browser.close().finally(() => { process.exitCode = 1 })
}, 30000)
try {
  const context = await browser.newContext({ serviceWorkers: 'block' })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(`${baseURL}/home`, { waitUntil: 'networkidle' })
  assert((await page.locator('body').innerText()).includes('microSched'))
  const cold = await page.evaluate(() => performance.getEntriesByType('resource').map(r => ({
    path: new URL(r.name).pathname, transfer: r.transferSize, decoded: r.decodedBodySize,
  })))
  await page.reload({ waitUntil: 'networkidle' })
  const warm = await page.evaluate(() => performance.getEntriesByType('resource')
    .filter(r => /\/assets\/.*\.(js|css)$/.test(new URL(r.name).pathname))
    .map(r => ({ path: new URL(r.name).pathname, transfer: r.transferSize })))
  assert(warm.length > 0 && warm.every(r => r.transfer === 0))
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({cold, warm, pageErrors: errors}))
  await context.close()

  const pwa = await browser.newContext({ serviceWorkers: 'allow' })
  const pwaPage = await pwa.newPage()
  pwaPage.on('console', message => {
    if (message.type() === 'error') console.error('PWA console:', message.text())
  })
  pwaPage.on('pageerror', error => console.error('PWA error:', error.message))
  await pwaPage.goto(`${baseURL}/home`, { waitUntil: 'networkidle' })
  console.log('PWA registrations:', await pwaPage.evaluate(async () =>
    (await navigator.serviceWorker.getRegistrations()).map(r => ({
      active: r.active?.state, waiting: r.waiting?.state, installing: r.installing?.state,
    }))))
  // Existing worker does not call clients.claim(); a normal next navigation
  // becomes controlled after activation. Do not change app lifecycle for QA.
  await pwaPage.waitForFunction(async () =>
    (await navigator.serviceWorker.getRegistrations()).some(r => r.active?.state === 'activated'),
    null, { timeout: 15000 })
  await pwaPage.reload({ waitUntil: 'networkidle' })
  await pwaPage.waitForFunction(() => navigator.serviceWorker.controller !== null,
    null, { timeout: 15000 })
  await pwa.setOffline(true)
  await pwaPage.reload({ waitUntil: 'networkidle' })
  assert((await pwaPage.locator('body').innerText()).includes('microSched'))
  await pwa.close()
  console.log(JSON.stringify({ environment: 'native local FastAPI, no DB, no throttling',
    cold, warm, pageErrors: errors, serviceWorkerOfflineShell: 'PASS',
    productionCapacity: 'NOT_MEASURED', physicalDevice: 'NOT_RUN' }, null, 2))
} finally {
  clearTimeout(deadline)
  await browser.close()
}
