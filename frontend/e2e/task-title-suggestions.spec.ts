import path from 'node:path'
import { expect, test } from './fixtures/tasks'
import type { Locator, Page } from '@playwright/test'

const today = (offset = 0) => new Date(Date.now() + 7 * 3_600_000 + offset * 86_400_000).toISOString().slice(0, 10)
const history = [
  { title: '[TRAINING] upper body', count: 2 },
  { title: '[TRAINING] lower body', count: 3 },
  { title: '[TRAINING] soul', count: 10 },
  { title: 'Đọc sách', count: 2 },
  { title: `Chuỗi ${'X'.repeat(70)} tiếng Việt có dấu 📚`, count: 1 },
]

const measurements = new WeakMap<Page, { api: number; titleSource: number; taskWrites: number }>()
test.beforeEach(async ({ page, taskApi }) => {
  const calls = { api: 0, titleSource: 0, taskWrites: 0 }
  measurements.set(page, calls)
  page.on('request', request => {
    const pathname = new URL(request.url()).pathname
    if (pathname.startsWith('/api/')) calls.api++
    if (pathname === '/api/tasks/title-suggestions') calls.titleSource++
    if (pathname.startsWith('/api/tasks') && request.method() !== 'GET') calls.taskWrites++
  })
  const template = taskApi.tasks[0]
  taskApi.tasks = history.map((row, index) => ({ ...template, title: row.title,
    id: `019a0e2e-0000-7000-8006-${String(index + 1).padStart(12, '0')}`,
    is_private: false, due_precision: 'date', due_on: today(), due_at: null, items: [] }))
  taskApi.tasks.push({ ...taskApi.tasks[0], id: '019a0e2e-0000-7000-8006-000000000099',
    title: 'PRIVATE SYNTHETIC SENTINEL', is_private: true })
  taskApi.privateUntil = new Date(Date.now() + 600_000).toISOString()
  await page.route('**/api/me', route => route.fulfill({ json: {
    email: 'qa@example.test', signed_in_at: '2026-11-16T00:00:00Z',
    expires_at: new Date(Date.now() + 86_400_000).toISOString(), private_until: taskApi.privateUntil,
    private_locked_until: null, pin_is_set: true, pin_is_bootstrap: false, mimi_available: false,
  } }))
  for (const pattern of ['**/api/calendar/**', '**/api/reminders/**', '**/api/reminder-history**', '**/api/settings**'])
    await page.route(pattern, route => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/tasks/title-suggestions', route => route.fulfill({ json: history }))
})

test.afterEach(async ({ page }, info) => {
  info.annotations.push({ type: 'synthetic-api-calls', description: JSON.stringify(measurements.get(page)) })
})

async function pendingRows(page: Page): Promise<number> {
  return page.evaluate(() => new Promise<number>((resolve, reject) => {
    const request = indexedDB.open('microsched-outbox-v1')
    request.onerror = () => reject(new Error('Cannot inspect synthetic outbox'))
    request.onsuccess = () => {
      const database = request.result
      const count = database.transaction('rows', 'readonly').objectStore('rows').count()
      count.onsuccess = () => { resolve(count.result); database.close() }
      count.onerror = () => { reject(new Error('Cannot count synthetic commands')); database.close() }
    }
  }))
}

async function firstSuggestion(page: Page, input: Locator, value = 'trainjing') {
  await input.fill(value)
  await expect(page.getByRole('option').first()).toHaveText('[TRAINING]')
  await input.press('Tab')
  await expect(input).toHaveValue('[TRAINING]')
  await expect(input).toBeFocused()
  await expect(page.getByRole('listbox')).toHaveCount(0)
}

async function evidence(page: Page, project: string, name: string) {
  if (process.env.B3_EVIDENCE_DIR)
    await page.screenshot({ path: path.join(process.env.B3_EVIDENCE_DIR, `${project}-${name}.png`), fullPage: false })
}

test('Calendar month: suggestions fill only; drag uses target day once through offline outbox', async ({ page, context, taskApi }, info) => {
  test.skip(info.project.name !== 'desktop', 'Desktop grid drag journey')
  const writes: string[] = []
  page.on('request', request => { if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/tasks') writes.push(request.postData() ?? '') })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Lịch', exact: true }).click()
  const input = page.getByTestId('calendar-quick-task-input')
  await firstSuggestion(page, input)
  await input.fill('[TRAINING] upp')
  await expect(page.getByRole('option').first()).toHaveText('[TRAINING] upper body')
  const fieldBox = await input.boundingBox()
  const listBox = await page.getByRole('listbox').boundingBox()
  expect(listBox!.width).toBeGreaterThan(fieldBox!.width - 12)
  expect(listBox!.x).toBeCloseTo(fieldBox!.x + 1, -1)
  await evidence(page, info.project.name, 'calendar-month-a')
  await page.keyboard.down('Enter')
  await page.keyboard.down('Enter')
  await page.keyboard.up('Enter')
  expect(writes).toHaveLength(0)
  expect(await pendingRows(page)).toBe(0)
  await expect(input).toHaveValue('[TRAINING] upper body')
  const targetDay = today(1)
  const target = page.locator(`[data-testid="calendar-day-cell"][data-day="${targetDay}"]`).first()
  await context.setOffline(true)
  const transfer = await page.evaluateHandle(() => new DataTransfer())
  await page.getByTestId('calendar-quick-task-draggable').dispatchEvent('dragstart', { dataTransfer: transfer })
  await target.dispatchEvent('drop', { dataTransfer: transfer })
  await expect.poll(() => pendingRows(page)).toBe(1)
  expect(writes).toHaveLength(0)
  await context.setOffline(false)
  await expect.poll(() => writes.length).toBe(1)
  await expect.poll(() => pendingRows(page)).toBe(0)
  const payload = JSON.parse(writes[0])
  expect(payload).toMatchObject({ title: '[TRAINING] upper body', due_precision: 'date', due_on: targetDay, is_private: false })
  expect(taskApi.tasks.filter(row => row.id === payload.id)).toHaveLength(1)
  await input.fill('A free grid draft')
  await input.press('Enter')
  await expect.poll(() => writes.length).toBe(2)
  expect(JSON.parse(writes[1])).toMatchObject({ title: 'A free grid draft', due_on: today(), is_private: false })
  await expect.poll(() => pendingRows(page)).toBe(0)
})

test('Calendar agenda: touch/keyboard fill preserves selected date, submits once, keeps focus', async ({ page, taskApi }, info) => {
  await page.goto('/')
  await page.getByRole('tab', { name: 'Lịch', exact: true }).click()
  await page.getByTestId('calendar-mode-toggle-agenda').click()
  await page.getByTestId('calendar-agenda-next-month').click()
  const before = await page.getByTestId('calendar-agenda-day-title').textContent()
  const input = page.getByTestId('calendar-agenda-quick-task-input')
  const count = taskApi.tasks.length
  await input.fill('[TRAINING] upp')
  const option = page.getByRole('option', { name: '[TRAINING] upper body', exact: true })
  await expect(option).toBeVisible()
  const fieldBox = await input.boundingBox()
  expect(fieldBox!.y).toBeGreaterThanOrEqual(0)
  expect(fieldBox!.y + fieldBox!.height).toBeLessThanOrEqual(page.viewportSize()!.height - (info.project.name === 'mobile' ? 58 : 0))
  await evidence(page, info.project.name, 'calendar-agenda-a')
  if (info.project.name === 'mobile') await option.tap()
  else await input.press('Enter')
  await expect(input).toHaveValue('[TRAINING] upper body')
  expect(taskApi.tasks).toHaveLength(count)
  expect(await pendingRows(page)).toBe(0)
  await expect(page.getByTestId('calendar-agenda-day-title')).toHaveText(before!)
  await input.press('Enter')
  await expect(input).toHaveValue('')
  await expect(input).toBeFocused()
  await expect.poll(() => taskApi.tasks.length).toBe(count + 1)
  expect(taskApi.tasks[0].title).toBe('[TRAINING] upper body')
  expect(taskApi.tasks[0].due_on?.slice(-2)).toBe('01')
  const nextMonth = new Date(`${today().slice(0, 7)}-01T00:00:00Z`)
  nextMonth.setUTCMonth(nextMonth.getUTCMonth() + 1)
  expect(taskApi.tasks[0].due_on).toBe(nextMonth.toISOString().slice(0, 10))
})

test('one lazy source across keystrokes and surfaces; Private title is absent while unlocked', async ({ page, taskApi }) => {
  let reads = 0
  await page.route('**/api/tasks/title-suggestions', route => { reads++; return route.fulfill({ json: history }) })
  await page.goto('/')
  expect(reads).toBe(0)
  const quick = page.getByTestId('quick-add-input')
  await quick.focus()
  await expect.poll(() => reads).toBe(1)
  for (const value of ['tr', 'train', 'trainjing', 'training', 'PRIVATE SYNTHETIC']) await quick.fill(value)
  await expect(page.getByRole('listbox')).toHaveCount(0)
  expect(taskApi.privateUntil).not.toBeNull()
  expect(reads).toBe(1)
  await quick.fill('')
  await page.getByRole('tab', { name: 'Lịch', exact: true }).click()
  await page.getByTestId('calendar-mode-toggle-agenda').click()
  await firstSuggestion(page, page.getByTestId('calendar-agenda-quick-task-input'))
  expect(reads).toBe(1)
  expect(await pendingRows(page)).toBe(0)
})

test('Quick Add: keyboard navigation, Escape and weak input retain normal form submit', async ({ page, taskApi }) => {
  await page.goto('/')
  const input = page.getByTestId('quick-add-input')
  const count = taskApi.tasks.length
  await input.fill('training')
  await expect(page.getByRole('option').first()).toHaveText('[TRAINING]')
  await input.press('ArrowDown')
  await input.press('Tab')
  await expect(input).toHaveValue('[TRAINING] soul')
  expect(taskApi.tasks).toHaveLength(count)
  await input.fill('trainjing')
  await expect(page.getByRole('listbox')).toBeVisible()
  await input.press('Escape')
  await expect(page.getByRole('listbox')).toHaveCount(0)
  await input.press('Tab')
  await expect(page.getByTestId('quick-add-submit')).toBeFocused()
  expect(taskApi.tasks).toHaveLength(count)
  await input.fill('xy')
  await expect(page.getByRole('listbox')).toHaveCount(0)
  await input.press('Enter')
  await expect(input).toHaveValue('')
  await expect(input).toBeFocused()
  await expect.poll(() => taskApi.tasks.length).toBe(count + 1)
  expect(taskApi.tasks[0]).toMatchObject({ title: 'xy', due_on: today() })
})

test('detailed title: IME never chooses/submits; popup Escape keeps dialog; chosen draft remains editable', async ({ page, taskApi }, info) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Thêm chi tiết', exact: true }).click()
  const input = page.getByTestId('task-title-input')
  const count = taskApi.tasks.length
  await input.fill('trainjing')
  await expect(page.getByRole('listbox')).toBeVisible()
  await input.dispatchEvent('compositionstart', { data: 'ế' })
  await input.press('Enter')
  await expect(input).toHaveValue('trainjing')
  expect(taskApi.tasks).toHaveLength(count)
  await input.dispatchEvent('compositionend', { data: 'ế' })
  await input.press('Escape')
  await expect(page.getByTestId('task-create-dialog')).toBeVisible()
  await expect(page.getByRole('listbox')).toHaveCount(0)
  await input.fill('[TRAINING] upp')
  await expect(page.getByRole('option').first()).toHaveText('[TRAINING] upper body')
  await evidence(page, info.project.name, 'detail-a')
  await input.press('Tab')
  await expect(input).toHaveValue('[TRAINING] upper body')
  expect(taskApi.tasks).toHaveLength(count)
  await input.fill('Tự nhập ĐỀ CƯƠNG 📚')
  await input.press('Enter')
  await expect(page.getByTestId('task-create-dialog')).toBeHidden()
  await expect.poll(() => taskApi.tasks.length).toBe(count + 1)
  expect(taskApi.tasks[0].title).toBe('Tự nhập ĐỀ CƯƠNG 📚')
})

test('normal submission still works when title suggestions fail', async ({ page, taskApi }) => {
  let reads = 0
  await page.route('**/api/tasks/title-suggestions', route => { reads++; return route.fulfill({ status: 503, json: { detail: 'Synthetic unavailable' } }) })
  await page.goto('/')
  const input = page.getByTestId('quick-add-input')
  const count = taskApi.tasks.length
  await input.fill('Một việc tự do 📚')
  await expect.poll(() => reads).toBe(1)
  await input.press('Enter')
  await expect.poll(() => taskApi.tasks.length).toBe(count + 1)
  expect(taskApi.tasks[0].title).toBe('Một việc tự do 📚')
  // Local admission and server ACK both invalidate Task queries; neither is typing.
  await expect.poll(() => pendingRows(page)).toBe(0)
  expect(reads).toBeGreaterThan(1)
  const afterMutation = reads
  await input.fill('Another free draft')
  await input.fill('A third free draft')
  expect(reads).toBe(afterMutation)
})


test('session visibility change purges suggestions and refocus loads fresh titles once', async ({ page }) => {
  let reads = 0
  await page.route('**/api/tasks/title-suggestions', route => { reads++; return route.fulfill({ json: reads === 1 ? history : [{ title: 'New source title', count: 1 }] }) })
  await page.goto('/')
  const input = page.getByTestId('quick-add-input')
  await input.fill('trainjing')
  await expect(page.getByRole('option').first()).toHaveText('[TRAINING]')
  await page.evaluate(() => window.dispatchEvent(new Event('microsched:visibility')))
  await expect(page.getByRole('listbox')).toHaveCount(0)
  expect(reads).toBe(1)
  await input.blur()
  await input.fill('New source')
  await expect(page.getByRole('option').first()).toHaveText('New source title')
  expect(reads).toBe(2)
})

test('malformed optional source cannot break ordinary title entry', async ({ page, taskApi }) => {
  await page.route('**/api/tasks/title-suggestions', route => route.fulfill({ json: { unexpected: 'synthetic' } }))
  await page.goto('/')
  const count = taskApi.tasks.length
  const input = page.getByTestId('quick-add-input')
  await input.fill('Free form after invalid source')
  await expect(page.getByRole('listbox')).toHaveCount(0)
  await input.press('Enter')
  await expect.poll(() => taskApi.tasks.length).toBe(count + 1)
})


test('invalidated titles stay hidden until the fresh STANDARD source arrives', async ({ page, taskApi }) => {
  let reads = 0
  let release: (() => void) | undefined
  const wait = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/tasks/title-suggestions', async route => {
    reads++
    if (reads > 1) await wait
    await route.fulfill({ json: reads === 1 ? history : [{ title: 'Fresh STANDARD title', count: 1 }] })
  })
  await page.goto('/')
  const input = page.getByTestId('quick-add-input')
  await input.fill('training')
  await expect(page.getByRole('listbox')).toBeVisible()
  const count = taskApi.tasks.length
  await input.fill('An ordinary new task')
  await input.press('Enter')
  await expect.poll(() => taskApi.tasks.length).toBe(count + 1)
  await expect.poll(() => reads).toBeGreaterThan(1)
  try {
    await input.fill('training')
    await expect(page.getByRole('listbox')).toHaveCount(0)
  } finally { release?.() }
  await input.fill('Fresh STANDARD')
  await expect(page.getByRole('option').first()).toHaveText('Fresh STANDARD title')
})
