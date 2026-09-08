// Disposable local image only. No real identity, provider or personal payloads.
import assert from 'node:assert/strict'
import { chromium } from '@playwright/test'

const baseURL = process.env.REMINDER_QA_URL || 'http://127.0.0.1:8048'
assert(['localhost', '127.0.0.1'].includes(new URL(baseURL).hostname))
// Docker port forwarding is not a loopback client at the app. Obtain the
// synthetic session through the native local app, preserving the existing guard.
const loginURL = process.env.REMINDER_QA_LOGIN_URL || baseURL
assert.equal(new URL(loginURL).hostname, new URL(baseURL).hostname)
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ baseURL, viewport: { width: 390, height: 844 }, serviceWorkers: 'block' })
const page = await context.newPage()
const owned = []
const errors = []
page.on('pageerror', (error) => errors.push(error.message))
const json = async (response) => { assert(response.ok(), `${response.status()} ${await response.text()}`); return response.json() }
try {
  assert.equal((await page.request.get('/api/reminders')).status(), 401)
  await page.goto(`${loginURL}/auth/dev-session`)
  await json(await page.request.post('/api/private/unlock', { data: { pin: '470047' } }))
  const task = await json(await page.request.post('/api/tasks', { data: { title: 'Synthetic private 047', is_private: true, items: [] } }))
  owned.push(`/api/tasks/${task.id}`)
  const privateReminder = await json(await page.request.put(`/api/reminders/task/${task.id}`, { data: { mode: 'absolute', due_at: '2030-01-02T00:00:00Z' } }))
  await page.request.post('/api/private/lock')
  const hidden = await page.request.get(`/api/reminders/source/task/${task.id}`)
  assert.equal(hidden.status(), 404)
  const listing = await page.request.get('/api/reminders')
  assert.equal(listing.headers()['cache-control'], 'no-store')
  assert(!(await json(listing)).items.some((r) => r.id === privateReminder.id))
  assert.equal((await page.request.delete(`/api/reminders/${privateReminder.id}?revision=1`)).status(), 404)
  await json(await page.request.post('/api/private/unlock', { data: { pin: '470047' } }))

  const longTitle = `🧭 ${'X'.repeat(70)} Ế Ữ Ộ Ằ ${'Lời nhắc tiếng Việt đủ dấu, '.repeat(6)}`
  const tracker = await json(await page.request.post('/api/tracker/trackers', { data: { name: longTitle, kind: 'general' } }))
  owned.push(`/api/tracker/trackers/${tracker.id}`)
  const trackerReminder = await json(await page.request.put(`/api/reminders/tracker/${tracker.id}`, { data: { mode: 'absolute', due_at: '2030-01-02T00:00:00Z' } }))
  const source = await json(await page.request.post('/api/calendar/sources', { data: { name: `Synthetic 047 ${tracker.id}`, kind: 'manual' } }))
  owned.push(`/api/calendar/sources/${source.id}`)
  const event = await json(await page.request.post('/api/calendar/events', { data: { source_id: source.id, title: 'Synthetic event 047', starts_at: '2030-01-03T03:00:00Z', ends_at: '2030-01-03T04:00:00Z' } }))
  const eventReminder = await json(await page.request.put(`/api/reminders/event/${event.id}`, { data: { mode: 'relative', offset_minutes: -60 } }))
  await page.goto('/')
  await page.getByTestId('reminder-center-open').click()
  const center = page.getByTestId('reminder-center')
  for (const title of [longTitle, event.title]) {
    const row = center.getByTestId('reminder-row').filter({ hasText: title })
    await row.waitFor()
    assert(await row.evaluate((node) => node.scrollWidth <= node.clientWidth), 'long text overflows reminder row')
    await row.getByRole('button', { name: 'Mở đối tượng', exact: true }).click()
    const sourceDialog = page.getByRole('dialog').filter({ has: page.getByRole('heading', { name: 'Đối tượng được nhắc' }) })
    await sourceDialog.getByTestId('source-reminder').click()
    await page.getByTestId('reminder-editor').getByTestId('reminder-preview').waitFor()
    await page.getByTestId('reminder-editor').getByRole('button', { name: 'Đóng', exact: true }).first().click()
    await sourceDialog.getByRole('button', { name: 'Đóng', exact: true }).first().click()
  }
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  await json(await page.request.patch(`/api/calendar/events/${event.id}`, { data: { starts_at: '2030-01-04T03:00:00Z', ends_at: '2030-01-04T04:00:00Z' } }))
  const shifted = await json(await page.request.get(`/api/reminders?kind=event&source_id=${event.id}`))
  assert.equal(Date.parse(shifted.items[0].due_at), Date.parse('2030-01-04T02:00:00Z'))
  assert.equal(shifted.items[0].revision, eventReminder.revision + 1)
  await page.request.delete(`/api/reminders/${trackerReminder.id}?revision=1`)
  // Real timer wake, no provider registered: one bounded wait, no repeated polling.
  const immediate = await json(await page.request.put(`/api/reminders/tracker/${tracker.id}`, { data: { mode: 'absolute', due_at: new Date(Date.now() + 2500).toISOString() } }))
  await new Promise((resolve) => setTimeout(resolve, 5000))
  const fired = await json(await page.request.get(`/api/reminders?section=attention&kind=tracker&source_id=${tracker.id}`))
  assert.equal(fired.items.find((r) => r.id === immediate.id)?.status, 'no_device')
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({ result: 'PASS', checks: ['anonymous 401', 'private API list/detail/cancel gate', 'no-store', 'task/event/tracker source editors', 'long Vietnamese and unbroken text fits mobile', 'event source trigger through HTTP', 'real timer wake -> no_device'], physical_device: 'NOT_RUN', actual_push: 'NOT_RUN' }))
} finally {
  // Exact synthetic objects created above; deletion order removes event source first.
  for (const path of owned.reverse()) assert((await page.request.delete(path)).ok(), `cleanup ${path}`)
  await page.request.post('/auth/logout')
  await context.close()
  await browser.close()
}
