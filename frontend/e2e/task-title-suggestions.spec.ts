import path from 'node:path'
import { expect, test } from './fixtures/tasks'
import type { Locator, Page, Request } from '@playwright/test'

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
  for (const pattern of ['**/api/calendar/**', '**/api/reminders/**', '**/api/reminders?**', '**/api/reminder-history**', '**/api/settings**'])
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


/** Keep the real app/outbox/query cache; only the HTTP boundary is synthetic. */
function optionalSource(page: Page, mode: 'ok' | '503' | 'held' | 'timeout') {
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  let reads = 0
  const started = new WeakMap<Request, number>()
  const failures: number[] = []
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/api/tasks/title-suggestions')
      started.set(request, Date.now())
  })
  page.on('requestfailed', request => {
    if (new URL(request.url()).pathname === '/api/tasks/title-suggestions')
      failures.push(Date.now() - (started.get(request) ?? Date.now()))
  })
  const ready = page.route('**/api/tasks/title-suggestions', async route => {
    reads++
    if (mode === '503') return route.fulfill({ status: 503, json: { detail: 'Synthetic optional source unavailable' } })
    if (mode === 'held' || mode === 'timeout') await gate
    return route.fulfill({ json: history }).catch(() => {})
  })
  return { ready, release, reads: () => reads, failures }
}

async function ackPanel(page: Page, info: import('@playwright/test').TestInfo, server: () => unknown, check: () => Promise<void>) {
  await expect.poll(() => pendingRows(page)).toBe(0)
  const panel = page.getByTestId('outbox-panel')
  await expect(panel.getByText('Đã gửi hết', { exact: true })).toBeVisible()
  const receipt = { server: server(), durablePending: await pendingRows(page),
    reconcilingVisible: await panel.getByText('Đang đối chiếu dữ liệu vừa gửi…', { exact: true }).count() }
  await info.attach('server-ack-vs-reconciliation', { body: JSON.stringify(receipt, null, 2), contentType: 'application/json' })
  await page.screenshot({ path: info.outputPath('ack-vs-reconciliation.png') })
  await check()
  await info.attach('settled-reconciliation', { body: JSON.stringify({ server: server(),
    durablePending: await pendingRows(page),
    reconcilingVisible: await panel.getByText('Đang đối chiếu dữ liệu vừa gửi…', { exact: true }).count(),
  }, null, 2), contentType: 'application/json' })
  await page.screenshot({ path: info.outputPath('reconciliation-settled.png') })
}

async function moveTwice(page: Page, taskId: string) {
  for (let offset = 1; offset <= 2; offset++) {
    await page.locator(`[data-testid="calendar-day-cell"][data-day="${today(offset - 1)}"]`).first().click()
    const row = page.getByTestId('calendar-day-dialog').locator(`[data-task-id="${taskId}"]`)
    await row.getByTestId('calendar-task-move').click()
    const move = page.getByTestId('calendar-move-dialog')
    await move.getByLabel('Ngày mới').fill(today(offset))
    await move.getByLabel('Ngày mới').press('Enter')
    await expect(move).toBeHidden({ timeout: 5_000 })
    await expect.poll(() => pendingRows(page)).toBe(0)
  }
}

for (const mode of ['ok', '503', 'held', 'timeout'] as const) {
  test(`B3-1 create ACK clears RAM barrier before two day moves (${mode})`, async ({ page, taskApi }, info) => {
    test.skip(mode === 'timeout' && info.project.name === 'mobile', 'One real 20-second timeout representative; both viewports cover held/503')
    test.setTimeout(mode === 'timeout' ? 40_000 : 30_000)
    const source = optionalSource(page, mode)
    await source.ready
    let releaseAck!: () => void
    const ack = new Promise<void>(resolve => { releaseAck = resolve })
    await page.route('**/api/tasks', async route => {
      if (route.request().method() === 'POST') await ack
      return route.fallback()
    })
    try {
      await page.goto('/')
      await page.getByRole('tab', { name: 'Lịch', exact: true }).click()
      if (info.project.name === 'mobile') await page.getByTestId('calendar-mode-toggle-agenda').click()
      const input = page.getByTestId(info.project.name === 'mobile' ? 'calendar-agenda-quick-task-input' : 'calendar-quick-task-input')
      await input.fill('B3-1 synthetic created task')
      await expect.poll(source.reads).toBe(1)
      await input.press('Enter')
      await expect(page.getByTestId('outbox-trigger')).toBeVisible()
      await page.getByTestId('outbox-trigger').click()
      releaseAck()
      await expect.poll(() => taskApi.tasks.some(row => row.title === 'B3-1 synthetic created task')).toBe(true)
      const created = taskApi.tasks.find(row => row.title === 'B3-1 synthetic created task')!
      await ackPanel(page, info, () => ({ id: created.id, title: created.title }), async () => {
        await expect(page.getByTestId('outbox-panel').getByText('Đang đối chiếu dữ liệu vừa gửi…', { exact: true })).toHaveCount(0)
      })
      await page.keyboard.press('Escape')
      if (mode === 'timeout') await expect.poll(() => source.failures.some(age => age >= 19_000), { timeout: 25_000 }).toBe(true)
      if (info.project.name === 'mobile') await page.getByTestId('calendar-mode-toggle-grid').click()
      await moveTwice(page, created.id)
      expect(created.due_on).toBe(today(2))
      expect(taskApi.tasks.filter(row => row.id === created.id)).toHaveLength(1)
      await page.screenshot({ path: info.outputPath('second-move-ack.png') })
    } finally { releaseAck?.(); source.release() }
  })
}

for (const mode of ['ok', '503', 'held'] as const) {
  test(`B3-1 edit ACK clears RAM barrier before reminder write (${mode})`, async ({ page, taskApi }, info) => {
    const source = optionalSource(page, mode)
    await source.ready
    const task = taskApi.tasks[0]
    let reminderWrites = 0
    await page.route('**/api/reminders/source/task/' + task.id, route => route.fulfill({ json: {
      title: task.title, is_private: false, open: true, anchor_at: null, anchor_day: task.due_on,
      date_only: true, updated_at: task.updated_at,
    } }))
    await page.route('**/api/reminders/task/' + task.id, async route => {
      if (route.request().method() === 'PUT') {
        reminderWrites++
        return route.fulfill({ json: { id: 'synthetic-reminder', revision: 1, ...route.request().postDataJSON() } })
      }
      return route.fulfill({ json: { items: [] } })
    })
    let releaseAck!: () => void
    const ack = new Promise<void>(resolve => { releaseAck = resolve })
    await page.route('**/api/tasks/' + task.id, async route => {
      if (route.request().method() === 'PATCH') await ack
      return route.fallback()
    })
    try {
      await page.goto('/')
      await page.getByTestId('quick-add-input').focus()
      await expect.poll(source.reads).toBe(1)
      const card = page.locator(`[data-testid="task-card"][data-task-id="${task.id}"]`)
      await card.getByTestId('task-edit').click()
      const dialog = page.getByTestId('task-detail-dialog')
      await dialog.getByTestId('task-title-input').fill('B3-1 synthetic edited task')
      await dialog.getByRole('button', { name: 'Lưu thay đổi', exact: true }).click()
      await page.keyboard.press('Escape')
      await page.getByTestId('outbox-trigger').click()
      releaseAck()
      await expect.poll(() => task.title).toBe('B3-1 synthetic edited task')
      await ackPanel(page, info, () => ({ id: task.id, title: task.title }), async () => {
        await expect(page.getByTestId('outbox-panel').getByText('Đang đối chiếu dữ liệu vừa gửi…', { exact: true })).toHaveCount(0)
      })
      await page.keyboard.press('Escape')
      await card.getByTestId('task-title').click()
      await page.getByTestId('task-detail-dialog').getByTestId('source-reminder').click()
      const reminder = page.getByTestId('reminder-editor')
      await reminder.getByRole('button', { name: 'Bật nhắc nhở', exact: true }).click()
      await reminder.getByTestId('reminder-absolute').fill(`${today(2)}T12:00`)
      await reminder.getByTestId('reminder-save').click()
      await expect(reminder).toBeHidden({ timeout: 5_000 })
      expect(reminderWrites).toBe(1)
      expect(await pendingRows(page)).toBe(0)
      await page.screenshot({ path: info.outputPath('edit-then-reminder-ack.png') })
    } finally { releaseAck?.(); source.release() }
  })
}

test('B3-1 required canonical failure retains reconciliation barrier', async ({ page, taskApi }, info) => {
  await page.goto('/')
  await page.getByRole('tab', { name: 'Lịch', exact: true }).click()
  if (info.project.name === 'mobile') await page.getByTestId('calendar-mode-toggle-agenda').click()
  const input = page.getByTestId(info.project.name === 'mobile' ? 'calendar-agenda-quick-task-input' : 'calendar-quick-task-input')
  let releaseAck!: () => void
  const ack = new Promise<void>(resolve => { releaseAck = resolve })
  let canonicalFails = false
  await page.route('**/api/tasks?**', route => canonicalFails
    ? route.fulfill({ status: 503, json: { detail: 'Synthetic required read unavailable' } }) : route.fallback())
  await page.route('**/api/tasks', async route => {
    if (route.request().method() === 'POST') { await ack; canonicalFails = true }
    return route.fallback()
  })
  try {
    await input.fill('B3-1 canonical guarded task')
    await input.press('Enter')
    await page.getByTestId('outbox-trigger').click()
    releaseAck()
    await expect.poll(() => taskApi.tasks.some(row => row.title === 'B3-1 canonical guarded task')).toBe(true)
    await ackPanel(page, info, () => ({ canonicalFails }), async () => {
      await expect(page.getByTestId('outbox-panel').getByText('Đang đối chiếu dữ liệu vừa gửi…', { exact: true })).toBeVisible()
    })
    await page.keyboard.press('Escape')
    if (info.project.name === 'mobile') await page.getByTestId('calendar-mode-toggle-grid').click()
    const created = taskApi.tasks.find(row => row.title === 'B3-1 canonical guarded task')!
    await page.locator(`[data-testid="calendar-day-cell"][data-day="${today()}"]`).first().click()
    await page.getByTestId('calendar-day-dialog').locator(`[data-task-id="${created.id}"]`).getByTestId('calendar-task-move').click()
    const move = page.getByTestId('calendar-move-dialog')
    await move.getByLabel('Ngày mới').fill(today(1))
    await move.getByLabel('Ngày mới').press('Enter')
    await expect(move.getByTestId('calendar-move-error')).toContainText('thay đổi đang chờ')
    expect(created.due_on).toBe(today())
  } finally { canonicalFails = false; releaseAck?.() }
})


test('B3-1 moved-to-Private title disappears before optional source revalidation finishes', async ({ page, taskApi }, info) => {
  const task = taskApi.tasks[0]
  let reads = 0
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/tasks/title-suggestions', async route => {
    reads++
    if (reads > 1) await gate
    await route.fulfill({ json: task.is_private ? history.filter(row => row.title !== task.title) : history }).catch(() => {})
  })
  try {
    await page.goto('/')
    const input = page.getByTestId('quick-add-input')
    await input.fill('[TRAINING] upp')
    await expect(page.getByRole('option').first()).toHaveText(task.title)
    await input.press('Escape')
    await input.fill('')
    await page.locator(`[data-testid="task-card"][data-task-id="${task.id}"]`).getByTestId('task-edit').click()
    const dialog = page.getByTestId('task-detail-dialog')
    await dialog.getByRole('checkbox', { name: 'Riêng tư', exact: true }).check()
    await dialog.getByRole('button', { name: 'Lưu thay đổi', exact: true }).click()
    await page.keyboard.press('Escape')
    await expect.poll(() => task.is_private).toBe(true)
    await expect.poll(() => pendingRows(page)).toBe(0)
    await expect.poll(() => reads).toBeGreaterThan(1)
    await input.fill('[TRAINING] upp')
    await expect(page.getByRole('listbox')).toHaveCount(0)
    await page.screenshot({ path: info.outputPath('private-title-invalidated.png') })
    release()
    await input.fill('[TRAINING] lower')
    await expect(page.getByRole('option').first()).toHaveText('[TRAINING] lower body')
    await input.fill('[TRAINING] upp')
    await expect(page.getByRole('listbox')).toHaveCount(0)
  } finally { release?.() }
})


function deferred() {
  let release!: () => void
  const wait = new Promise<void>(resolve => { release = resolve })
  return { wait, release }
}

for (const cache of ['initial', 'cached'] as const) {
  test(`B3 stale source race: ${cache} GET sampled before Private cannot offer its title after ACK`, async ({ page, taskApi }, info) => {
    const task = taskApi.tasks[0]
    const taskPath = `/api/tasks/${task.id}`
    const oldSource = deferred()
    const newSource = deferred()
    const write = deferred()
    const staleRequests = new Set<Request>()
    const outcomes = new Map<Request, 'finished' | 'aborted'>()
    let hold = cache === 'initial'
    let freshReads = 0
    let privatePatch: Request | undefined
    page.on('requestfinished', request => { if (staleRequests.has(request)) outcomes.set(request, 'finished') })
    page.on('requestfailed', request => { if (staleRequests.has(request)) outcomes.set(request, 'aborted') })
    await page.route('**/api/tasks/title-suggestions', async route => {
      // Freeze the response when the mock server samples it, not when we release it.
      const sample = task.is_private ? history.filter(row => row.title !== task.title) : history
      if (task.is_private) {
        freshReads++
        await newSource.wait
      } else if (hold) {
        staleRequests.add(route.request())
        await oldSource.wait
      }
      try { await route.fulfill({ json: sample }) }
      catch (error) { if (!route.request().failure()) throw error }
    })
    await page.route(url => url.pathname === taskPath, async route => {
      if (route.request().method() === 'PATCH') {
        privatePatch = route.request()
        await write.wait
      }
      await route.fallback()
    })
    try {
      await page.goto('/')
      const input = page.getByTestId('quick-add-input')
      const staleOption = page.getByRole('option', { name: task.title, exact: true })
      await input.fill('[TRAINING] upp')
      if (cache === 'cached') {
        await expect(staleOption).toBeVisible()
        hold = true
        await input.fill('B3 synthetic task to start a cached refetch')
        await input.press('Enter')
      }
      await expect.poll(() => staleRequests.size).toBeGreaterThan(0)
      await input.fill('')
      await page.locator(`[data-testid="task-card"][data-task-id="${task.id}"]`).getByTestId('task-edit').click()
      const dialog = page.getByTestId('task-detail-dialog')
      await dialog.getByRole('checkbox', { name: 'Riêng tư', exact: true }).check()
      await dialog.getByRole('button', { name: 'Lưu thay đổi', exact: true }).click()
      await expect.poll(() => privatePatch?.postDataJSON()).toMatchObject({ is_private: true })
      await expect.poll(() => pendingRows(page)).toBe(1)
      expect(task.is_private).toBe(false)
      if (await dialog.isVisible()) await page.keyboard.press('Escape')
      await page.getByTestId('outbox-trigger').click({ timeout: 5000 })

      const ack = page.waitForResponse(response => response.request() === privatePatch && response.ok())
      const canonical = page.waitForResponse(response => task.is_private && response.ok() &&
        response.request().method() === 'GET' && new URL(response.url()).pathname === '/api/tasks/timeline')
      write.release()
      expect(await (await ack).json()).toMatchObject({ id: task.id, is_private: true })
      await canonical
      await ackPanel(page, info, () => ({ privateAck: task.is_private, staleGets: staleRequests.size }), async () => {
        await expect(page.getByTestId('outbox-panel').getByText('Đang đối chiếu dữ liệu vừa gửi…', { exact: true })).toHaveCount(0)
      })
      await page.keyboard.press('Escape')
      await expect(page.getByTestId('outbox-panel')).toBeHidden()

      await page.evaluate(title => {
        const root = document.documentElement
        const record = () => {
          if ([...document.querySelectorAll('[role="option"]')].some(option => option.textContent === title))
            root.setAttribute('data-stale-title-offered', 'true')
        }
        new MutationObserver(record).observe(document.body, { subtree: true, childList: true, characterData: true })
        record()
      }, task.title)
      const staleOffered = async () => await page.locator('html').getAttribute('data-stale-title-offered') === 'true'
      // Interact after the modal releases focus instead of racing its close autofocus.
      await input.click()
      await input.fill('[TRAINING] upp')
      await expect(input).toBeFocused()
      await expect(staleOption).toHaveCount(0)
      oldSource.release()
      await expect.poll(() => outcomes.size).toBe(staleRequests.size)
      await expect.poll(async () => freshReads > 0 || await staleOffered()).toBe(true)
      expect(await staleOffered(), 'pre-Private response must never reopen the old option').toBe(false)
      await page.screenshot({ path: info.outputPath('old-response-released.png') })

      newSource.release()
      await input.fill('[TRAINING] lower')
      await expect(page.getByRole('option', { name: '[TRAINING] lower body', exact: true })).toBeVisible()
      await page.screenshot({ path: info.outputPath('fresh-standard-remains-usable.png') })
      await input.fill('[TRAINING] upp')
      await expect(staleOption).toHaveCount(0)
      expect(await staleOffered()).toBe(false)
      expect(taskApi.count('PATCH', taskPath)).toBe(1)
    } finally {
      await info.attach('stale-source-race', { body: JSON.stringify({
        sampledWhileStandard: staleRequests.size, oldRequests: [...outcomes.values()],
        hostedPrivate: task.is_private, freshReads, durablePending: await pendingRows(page).catch(() => null),
      }), contentType: 'application/json' })
      write.release()
      oldSource.release()
      newSource.release()
    }
  })
}


test('Task freshness stays live while the optional title source is held or fails', async ({ page, taskApi }, info) => {
  const source = deferred()
  let reads = 0
  await page.route('**/api/tasks/title-suggestions', async route => {
    reads++
    await source.wait
    await route.fulfill({ status: 503, json: { detail: 'Synthetic optional source unavailable' } })
  })
  try {
    await page.goto('/')
    const task = taskApi.tasks[0]
    await expect(page.locator(`[data-testid="task-card"][data-task-id="${task.id}"]`)).toBeVisible()
    expect(reads).toBe(0)
    const status = page.getByTestId('app-live-status')
    const input = page.getByTestId('quick-add-input')
    await input.fill('[TRAINING] upp')
    await expect.poll(() => reads).toBe(1)
    await expect.soft(status, 'canonical Task data is live while the optional GET is held')
      .toHaveAttribute('data-state', 'live', { timeout: 3000 })
    await evidence(page, info.project.name, 'task-live-optional-held')

    const failure = page.waitForResponse(response => new URL(response.url()).pathname === '/api/tasks/title-suggestions' &&
      response.status() === 503)
    source.release()
    expect(await (await failure).finished()).toBeNull()
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
    await expect(status, 'the optional 503 does not change canonical Task freshness').toHaveAttribute('data-state', 'live')
    await expect(input).toHaveValue('[TRAINING] upp')
    await expect(page.getByRole('option')).toHaveCount(0)
    await evidence(page, info.project.name, 'task-live-optional-503')
  } finally { source.release() }
})
