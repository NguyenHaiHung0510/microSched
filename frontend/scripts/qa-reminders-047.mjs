// Real local-app smoke. Synthetic data only; no browser profile or real push provider.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from '@playwright/test'

const baseURL = process.env.REMINDER_QA_URL || 'http://127.0.0.1:8047'
const target = new URL(baseURL)
assert(['127.0.0.1', 'localhost'].includes(target.hostname), 'local disposable app only')
const browser = await chromium.launch({ headless: true })
const out = 'output/playwright/reminders-047'
await mkdir(out, { recursive: true })
const results = []
try {
  for (const viewport of [{ width: 390, height: 844 }, { width: 1280, height: 800 }]) {
    const context = await browser.newContext({ baseURL, viewport, serviceWorkers: 'block' })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    let task
    const checked = async (response) => { assert(response.ok(), `${response.status()} ${await response.text()}`); return response.json() }
    try {
      await page.goto('/auth/dev-session')
      task = await checked(await page.request.post('/api/tasks', { data: {
        title: `Nhắc một lần · kiểm tra ${viewport.width}`, due_precision: 'none', items: [],
      } }))
      await page.goto('/')
      const card = page.locator(`[data-testid="task-card"][data-task-id="${task.id}"]`)
      await card.getByTestId('task-title').click()
      await page.getByTestId('task-detail-dialog').getByTestId('source-reminder').click()
      let editor = page.getByTestId('reminder-editor')
      await editor.getByRole('button', { name: 'Bật nhắc nhở', exact: true }).click()
      await editor.getByTestId('reminder-absolute').fill('2030-01-02T20:00')
      assert.match(await editor.getByTestId('reminder-preview').innerText(), /20:00/)
      await editor.getByTestId('reminder-save').click()
      await editor.waitFor({ state: 'hidden' })
      await page.getByTestId('task-detail-dialog').getByRole('button', { name: 'Đóng', exact: true }).first().click()
      await page.getByTestId('reminder-center-open').click()
      const center = page.getByTestId('reminder-center')
      await center.getByTestId('reminder-row').filter({ hasText: task.title }).waitFor()
      assert.equal(await page.evaluate(() => innerWidth), viewport.width)
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      const geometry = await center.locator('button:visible').evaluateAll((nodes) => nodes.map((node) => {
        const r = node.getBoundingClientRect(); return { text: node.textContent, w: r.width, h: r.height }
      }))
      assert(geometry.every((g) => g.w >= 44 && g.h >= 44), JSON.stringify(geometry))
      await page.screenshot({ path: `${out}/center-${viewport.width}.png`, fullPage: true })
      await checked(await page.request.patch(`/api/tasks/${task.id}`, { data: {
        due_precision: 'datetime', due_at: '2030-01-03T03:00:00Z', due_on: null,
      } }))
      await center.getByTestId('reminder-row').filter({ hasText: task.title }).getByRole('button', { name: 'Sửa / tắt nhắc' }).click()
      editor = page.getByTestId('reminder-editor')
      await editor.getByRole('combobox', { name: 'Cách đặt' }).click()
      await page.getByRole('option', { name: 'Trước / sau mốc đã lưu' }).click()
      await editor.getByRole('button', { name: '1 giờ trước', exact: true }).click()
      assert.match(await editor.getByTestId('reminder-preview').innerText(), /09:00/)
      await page.screenshot({ path: `${out}/relative-${viewport.width}.png`, fullPage: true })
      await editor.getByTestId('reminder-save').click()
      await editor.waitFor({ state: 'hidden' })
      let data = await checked(await page.request.get(`/api/reminders?section=active&kind=task&source_id=${task.id}`))
      assert.equal(data.items.length, 1)
      assert.equal(data.items[0].offset_minutes, -60)
      const active = data.items[0]
      await checked(await page.request.patch(`/api/tasks/${task.id}`, { data: { status: 'completed' } }))
      data = await checked(await page.request.get(`/api/reminders?section=all&kind=task&source_id=${task.id}`))
      assert.equal(data.items.find((r) => r.id === active.id).status, 'cancelled')
      assert.deepEqual(errors, [])
      results.push({ viewport, result: 'PASS', assertions: ['undated custom reminder', 'center', 'geometry', 'relative preset', 'source completion cancels'] })
    } finally {
      if (task) await page.request.delete(`/api/tasks/${task.id}`)
      await page.request.post('/auth/logout')
      await context.close()
    }
  }
} finally {
  await browser.close()
}
console.log(JSON.stringify({ results, physical_iphone: 'NOT_RUN', outbound_push: 'NOT_RUN' }, null, 2))
