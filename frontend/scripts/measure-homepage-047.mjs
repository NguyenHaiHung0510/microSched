// Bounded, unauthenticated local measurement; never target production.
import assert from 'node:assert/strict'
import { chromium } from '@playwright/test'
const baseURL = process.env.HOMEPAGE_QA_URL || 'http://127.0.0.1:8048'
assert(['127.0.0.1', 'localhost'].includes(new URL(baseURL).hostname))
const browser = await chromium.launch({ headless: true })
try {
  const context = await browser.newContext({ serviceWorkers: 'block', viewport: { width: 390, height: 844 } })
  const page = await context.newPage()
  await page.goto(baseURL, { waitUntil: 'networkidle' })
  await page.evaluate(() => document.fonts.ready)
  const cold = await page.evaluate(() => ({
    paint: performance.getEntriesByType('paint').map((r) => ({ name: r.name, ms: r.startTime })),
    resources: performance.getEntriesByType('resource').map((r) => ({ path: new URL(r.name).pathname, bytes: r.transferSize, decoded: r.decodedBodySize })),
  }))
  const paths = ['/', cold.resources.find((r) => r.path.endsWith('.js') && r.path.includes('/assets/')).path, '/api/me']
  const headers = []
  for (const path of paths) {
    const response = await fetch(baseURL + path)
    await response.arrayBuffer()
    headers.push({ path, status: response.status, cache: response.headers.get('cache-control'), encoding: response.headers.get('content-encoding'), etag: response.headers.get('etag') })
  }
  const samples = []
  // Fixed 64 requests, four workers, 5-second per-request timeout. Small burst,
  // not a capacity estimate, load-to-failure experiment or DDoS simulation.
  await Promise.all(Array.from({ length: 4 }, async (_, worker) => {
    for (let i = 0; i < 16; i++) {
      const path = paths[(worker + i) % paths.length]
      const start = performance.now()
      const response = await fetch(baseURL + path, { signal: AbortSignal.timeout(5000) })
      await response.arrayBuffer()
      samples.push({ path, status: response.status, ms: performance.now() - start })
    }
  }))
  const timings = samples.map((s) => s.ms).sort((a, b) => a - b)
  assert(samples.every((s) => s.status === (s.path === '/api/me' ? 401 : 200)))
  console.log(JSON.stringify({ environment: 'Docker local 1 CPU / 256 MB; no network throttling; service worker blocked', cold, headers, burst: { requests: samples.length, concurrency: 4, unexpected_statuses: 0, p50_ms: timings[31], p95_ms: timings[60], max_ms: timings[63] }, internet_and_DDoS_capacity: 'NOT_MEASURED' }, null, 2))
  await context.close()
} finally { await browser.close() }
