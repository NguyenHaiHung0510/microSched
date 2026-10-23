/** Bounded 093 author confidence; public synthetic rows only, no product acceptance. */
import fs from 'node:fs/promises'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { randomUUID } from 'node:crypto'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
const execute = promisify(execFile)
const wt = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..')
const require = createRequire(path.join(wt, 'frontend/package.json'))
const { chromium, expect } = require('@playwright/test')
const args = process.argv.slice(2)
function arg(name) { const i = args.indexOf(name); if (i < 0 || !args[i + 1]) throw Error('EXPLICIT_ARGUMENT_REQUIRED'); return args[i + 1] }
const origin = new URL(arg('--origin')).origin
if (origin !== 'http://127.0.0.1:4176') throw Error('OWN_093_ORIGIN_REQUIRED')
const output = path.resolve(arg('--output'))
const allowed = [path.join(wt, '.local/r8-093'), path.resolve(wt, '../../harness-reports/mimi-qa-2026-oct-19-owner296/dev-2026-oct-22/techlead/o8-093-dev328')]
if (!allowed.some(root => output.startsWith(root + path.sep))) throw Error('OWN_OUTPUT_REQUIRED')
const python = arg('--python'), oracle = path.resolve(arg('--oracle'))
if (oracle !== path.join(wt, '.local/r8-093/oracle.py')) throw Error('OWN_SCOPED_ORACLE_REQUIRED')
await fs.mkdir(output, { recursive: false })
const nonce = randomUUID().slice(0, 8)
const day = new Date(Date.now() + 7 * 3600000 + 86400000).toISOString().slice(0, 10)
const tomorrow = new Date(Date.parse(day + 'T00:00:00Z') + 86400000).toISOString().slice(0, 10)
const receipt = { status: 'IN_PROGRESS', started: new Date().toISOString(), origin,
  role: 'synthetic-owner', viewport: { width: 390, height: 844 }, outcomes: [], wire: [], screenshots: [],
  manifest: { prefix: `R8-093-${nonce}`, source_id: null, event_id: null, retention: 'RETAIN_OWN_PUBLIC_SYNTHETIC' } }
const save = () => fs.writeFile(path.join(output, 'receipt.json'), JSON.stringify(receipt, null, 2))
await save()
let browser, context, page
const requests = []
const need = (ok, code) => { if (!ok) throw Error(code) }
async function call(route, method = 'GET', body) {
  const response = await context.request.fetch(origin + route, { method, data: body })
  return { status: response.status(), body: await response.json() }
}
async function canonical(label, expected = {}) {
  const response = await call(`/api/calendar/events?from=${encodeURIComponent(day + 'T00:00:00+07:00')}&to=${encodeURIComponent(tomorrow + 'T23:59:00+07:00')}`)
  const api = response.body.items.find(x => x.id === receipt.manifest.event_id)
  const { stdout } = await execute(python, ['-B', oracle, receipt.manifest.source_id, receipt.manifest.event_id], { windowsHide: true, timeout: 15000 })
  const pg = JSON.parse(stdout).event
  need(response.status === 200 && api && api.source_id === receipt.manifest.source_id, 'OWN_CANONICAL_EVENT_REQUIRED')
  for (const key of ['starts_at', 'ends_at']) need(Date.parse(api[key]) === Date.parse(pg[key]), 'API_PG_TIME_MISMATCH')
  for (const key of ['id', 'source_id', 'title', 'all_day', 'location', 'description_md']) need(api[key] === pg[key], 'API_PG_FIELD_MISMATCH')
  for (const [key, value] of Object.entries(expected)) need(key.endsWith('_at') ? Date.parse(api[key]) === Date.parse(value) : api[key] === value, 'INTENDED_EDIT_NOT_PERSISTED')
  need(api.location === 'Phòng synthetic' && api.description_md === 'Mô tả public giữ nguyên', 'EVENT_TEXT_NOT_PRESERVED')
  receipt.outcomes.push({ label, status: 'PASS', expected, api, pg })
  await save()
  return api
}
async function listEdit() {
  await page.getByTestId('calendar-view-toggle-list').click()
  const current = await canonical('list-open-canonical')
  await page.getByRole('button', { name: 'Sửa buổi ' + current.title, exact: true }).click()
  await page.getByTestId('calendar-event-form').waitFor()
}
async function dayEdit() {
  await page.getByTestId('calendar-view-toggle-grid').click()
  const cell = page.locator(`[data-testid="calendar-day-cell"][data-day="${day}"]`)
  await cell.scrollIntoViewIfNeeded(); await cell.click()
  await page.locator(`[data-testid="calendar-day-event"][data-event-id="${receipt.manifest.event_id}"]`).click()
  await page.getByTestId('calendar-event-form').waitFor()
}
const form = () => page.getByTestId('calendar-event-form')
const times = () => form().locator('input[type="datetime-local"]')
async function submit() {
  const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/calendar/events/' + receipt.manifest.event_id && r.request().method() === 'PATCH')
  await form().getByRole('button', { name: 'Lưu buổi', exact: true }).click()
  need((await response).status() === 200, 'VALID_EDIT_MUST_SAVE')
  await form().waitFor({ state: 'hidden' })
}
async function invalid(label, end) {
  const before = await canonical(label + '-before')
  await times().nth(1).fill(end)
  const count = requests.length
  await form().getByRole('button', { name: 'Lưu buổi', exact: true }).click()
  const error = form().getByTestId('calendar-event-interval-error')
  await expect(error).toHaveText('Thời gian kết thúc phải sau thời gian bắt đầu.')
  await expect(times().nth(1)).toBeFocused()
  await expect(times().nth(1)).toHaveAttribute('aria-invalid', 'true')
  await expect(times().nth(1)).toHaveValue(end)
  const after = await canonical(label + '-after')
  need(JSON.stringify(before) === JSON.stringify(after) && requests.length === count, 'INVALID_MUST_SEND_ZERO_HTTP_AND_KEEP_ROW')
  const image = label + '.png'
  await form().screenshot({ path: path.join(output, image) })
  receipt.screenshots.push(image)
  receipt.outcomes.push({ label, status: 'PASS', invalid_http: requests.length - count,
    focus_end: true, draft_end: end, aria_describedby: await times().nth(1).getAttribute('aria-describedby') })
  await save()
}
try {
  need(require('@playwright/test/package.json').version === '1.62.1', 'CACHED_REVIEWED_PLAYWRIGHT_REQUIRED')
  browser = await chromium.launch({ headless: true })
  context = await browser.newContext({ viewport: receipt.viewport, serviceWorkers: 'allow' })
  context.setDefaultTimeout(12000)
  await context.route('**/*', route => {
    const url = new URL(route.request().url())
    return url.protocol === 'http:' && url.hostname === '127.0.0.1' && ['4176', '8003'].includes(url.port)
      ? route.continue() : route.abort('blockedbyclient')
  })
  context.on('request', r => { if (r.method() === 'PATCH' && new URL(r.url()).pathname.startsWith('/api/calendar/events/')) requests.push({ method: r.method(), path: new URL(r.url()).pathname }) })
  page = await context.newPage()
  await page.goto(origin + '/auth/dev-session'); await page.waitForURL(origin + '/')
  const me = await call('/api/me'); need(me.status === 200 && me.body.email === 'owner@test.local', 'SYNTHETIC_ROLE_REQUIRED')
  await page.getByRole('tab', { name: 'Lịch', exact: true }).click()
  await page.getByTestId('calendar-view-toggle-list').click()
  await page.getByTestId('calendar-manual-source-button').click()
  await page.getByLabel('Tên nguồn lịch').fill(receipt.manifest.prefix)
  const sourceResponse = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/calendar/sources')
  await page.getByRole('button', { name: 'Tạo nguồn', exact: true }).click()
  const sr = await sourceResponse; const source = await sr.json()
  receipt.manifest.source_id = source.id; await save(); need(sr.status() === 201, 'SOURCE_CREATE_FAILED')
  await page.getByRole('button', { name: 'Thêm buổi', exact: true }).click()
  await form().getByRole('textbox', { name: 'Tiêu đề', exact: true }).fill(receipt.manifest.prefix)
  await times().nth(0).fill(day + 'T08:00'); await times().nth(1).fill(day + 'T09:00')
  await form().getByRole('textbox', { name: 'Địa điểm', exact: true }).fill('Phòng synthetic')
  await form().getByRole('textbox', { name: 'Mô tả', exact: true }).fill('Mô tả public giữ nguyên')
  const createResponse = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/calendar/events')
  await form().getByRole('button', { name: 'Tạo buổi', exact: true }).click()
  const cr = await createResponse; const created = await cr.json()
  receipt.manifest.event_id = created.id; await save(); need(cr.status() === 201, 'EVENT_CREATE_FAILED')
  await form().waitFor({ state: 'hidden' }); await canonical('create', { starts_at: day + 'T08:00:00+07:00', ends_at: day + 'T09:00:00+07:00' })
  await listEdit(); await times().nth(0).fill(day + 'T08:15'); await submit(); await canonical('start-only', { starts_at: day + 'T08:15:00+07:00', ends_at: day + 'T09:00:00+07:00' })
  await listEdit(); await times().nth(1).fill(day + 'T09:15'); await submit(); await canonical('end-only', { starts_at: day + 'T08:15:00+07:00', ends_at: day + 'T09:15:00+07:00' })
  await listEdit(); await times().nth(0).fill(day + 'T09:30'); await times().nth(1).fill(day + 'T10:30'); await submit(); await canonical('both-same-day', { starts_at: day + 'T09:30:00+07:00', ends_at: day + 'T10:30:00+07:00' })
  await listEdit()
  await form().getByRole('textbox', { name: 'Tiêu đề', exact: true }).fill(receipt.manifest.prefix + '-draft')
  await invalid('list-equal-end', day + 'T09:30')
  await expect(form().getByRole('textbox', { name: 'Tiêu đề', exact: true })).toHaveValue(receipt.manifest.prefix + '-draft')
  await times().nth(1).fill(day + 'T10:45'); await expect(form().getByTestId('calendar-event-interval-error')).toHaveCount(0)
  await submit(); await canonical('list-corrected-with-draft', { title: receipt.manifest.prefix + '-draft', ends_at: day + 'T10:45:00+07:00' })
  await dayEdit(); await times().nth(0).fill(day + 'T23:30'); await times().nth(1).fill(tomorrow + 'T00:15'); await submit(); await canonical('day-cross-midnight', { starts_at: day + 'T23:30:00+07:00', ends_at: tomorrow + 'T00:15:00+07:00' })
  await page.keyboard.press('Escape')
  await dayEdit(); await invalid('day-earlier-end', day + 'T23:00')
  await times().nth(1).fill(tomorrow + 'T00:30'); await submit(); await canonical('day-corrected', { ends_at: tomorrow + 'T00:30:00+07:00' })
  await page.keyboard.press('Escape')
  await listEdit(); await form().getByRole('checkbox', { name: 'Cả ngày', exact: true }).check(); await submit()
  const allDay = await canonical('all-day', { starts_at: day + 'T00:00:00+07:00', ends_at: tomorrow + 'T00:00:00+07:00' })
  need(allDay.all_day && Date.parse(allDay.ends_at) - Date.parse(allDay.starts_at) === 86400000, 'ALL_DAY_BOUNDARY_MISMATCH')
  const beforeServer = await canonical('before-server-rejection')
  const rejected = await call('/api/calendar/events/' + receipt.manifest.event_id, 'PATCH', { starts_at: day + 'T09:00:00+07:00', ends_at: day + 'T09:00:00+07:00' })
  need(rejected.status === 422, 'BACKEND_INTERVAL_GUARD_REQUIRED')
  need(JSON.stringify(beforeServer) === JSON.stringify(await canonical('after-server-rejection')), 'REJECTED_ROW_CHANGED')
  receipt.server_validation = { status: 422, detail: 'ends_at must be after starts_at', row_unchanged: true }
  await page.reload(); await canonical('reloaded-canonical')
  receipt.status = 'AUTHOR_PASS'; receipt.finished = new Date().toISOString(); receipt.invalid_http = 0
} catch (error) {
  receipt.status = 'AUTHOR_FAIL'; receipt.error = /^[A-Z0-9_]+$/.test(error.message) ? error.message : 'AUTHOR_UI_STEP_FAILED_DETAILS_SUPPRESSED'
  receipt.finished = new Date().toISOString(); process.exitCode = 1
} finally {
  receipt.wire = requests
  await save()
  try { if (context) await context.request.post(origin + '/auth/logout') } finally { await context?.close(); await browser?.close() }
  console.log(JSON.stringify({ status: receipt.status, output, error: receipt.error, outcomes: receipt.outcomes.length }))
}
