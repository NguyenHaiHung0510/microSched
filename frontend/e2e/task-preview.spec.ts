import type { Locator, Page } from '@playwright/test'
import { expect, test as base, type FixtureTask } from './fixtures/tasks'

const taskId = '019a0e2e-0000-7000-8005-000000000001'
const LONG = 'Nội dung tiếng Việt đầy đủ 🌸\n' + 'Đ'.repeat(100) + '\n' + 'Chi tiết kiểm tra bố cục. '.repeat(80)
const task = (id: string, patch: Partial<FixtureTask> = {}): FixtureTask => ({ id, title: 'Chuẩn bị bản xem trước lịch tháng 10', body_md: 'Mô tả tổng hợp để chụp tooltip của tiêu đề task.',
  status: 'open', priority: 'p1', due_precision: 'date', due_on: '2026-10-20', due_at: null, is_private: false, pinned: true,
  items: [{ id: 'first', content: 'Kiểm tra luồng xem lịch', is_completed: true, position: 0 }, { id: 'second', content: 'Chụp ảnh desktop và mobile', is_completed: false, position: 1 }],
  created_at: '2026-10-20T00:00:00Z', updated_at: '2026-10-20T00:00:00Z', ...patch })
const test = base.extend<{ previewApi: { tasks: FixtureTask[]; requests: string[]; writes: object[]; errors: string[] } }>({
  previewApi: [async ({ page, taskApi }, use) => {
    taskApi.tasks = [task(taskId), task('preview-private', { title: 'Task riêng tư synthetic', body_md: 'Nội dung private synthetic', is_private: true, pinned: false })]
    const state = { tasks: taskApi.tasks, requests: [] as string[], writes: [] as object[], errors: [] as string[] }
    page.on('request', request => {
      const url = new URL(request.url())
      if (url.pathname.startsWith('/api/')) state.requests.push(`${request.method()} ${url.pathname}${url.search}`)
      if (url.pathname.startsWith('/api/tasks/') && request.method() === 'PATCH') state.writes.push(request.postDataJSON())
    })
    page.on('pageerror', error => state.errors.push(error.message))
    await page.route('**/api/calendar/**', route => route.fulfill({ json: { items: [] } }))
    await page.route('**/api/tasks?*', async route => {
      const url = new URL(route.request().url())
      if (url.searchParams.get('status') !== 'all' || !url.searchParams.has('from')) return route.fallback()
      const visible = taskApi.tasks.filter(task => !task.is_private || Boolean(taskApi.privateUntil))
      const cursor = url.searchParams.get('cursor')
      // Return a second page intentionally: the month fetch must keep the full task shape on every page.
      return route.fulfill({ json: { items: cursor ? visible.slice(1) : visible.slice(0, 1), next_cursor: !cursor && visible.length > 1 ? 'synthetic-page-2' : null } })
    })
    await use(state)
  }, { auto: true }],
})
const preview = (page: Page) => page.locator('[data-testid="task-preview"]:visible')
const card = (page: Page, id = taskId) => page.locator(`[data-testid="task-card"][data-task-id="${id}"]`)
const day = (page: Page, value = '2026-10-20') => page.locator(`[data-testid="calendar-day-cell"][data-day="${value}"]`).first()
const chip = (page: Page) => day(page).getByTestId('calendar-day-chip-task').filter({ hasText: 'Chuẩn bị bản xem trước lịch tháng 10' })
async function calendar(page: Page) {
  await page.getByRole('tab', { name: 'Lịch', exact: true }).click()
  await day(page).scrollIntoViewIfNeeded()
}
async function shot(page: Page, name: string) { if (process.env.TASK_PREVIEW_EVIDENCE_DIR) await page.screenshot({ path: `${process.env.TASK_PREVIEW_EVIDENCE_DIR}/${name}.png`, animations: 'disabled' }) }
async function fits(locator: Locator) { return locator.evaluate(node => { const r = node.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight && node.scrollWidth <= node.clientWidth }) }

test.beforeEach(async ({ page }) => { await page.clock.setFixedTime(new Date('2026-10-20T07:00:00Z')) })
test.afterEach(async ({ previewApi }, info) => {
  await info.attach('synthetic-request-receipt', { body: JSON.stringify(previewApi), contentType: 'application/json' })
  expect(previewApi.errors).toEqual([])
})

test('shared rich light preview on Task title and month chip; keyboard focus and full-detail clicks remain', async ({ page, previewApi }, info) => {
  test.skip(info.project.name !== 'desktop', 'Mobile uses the existing full task path.')
  await page.goto('/')
  const title = card(page).getByTestId('task-title')
  await title.hover()
  await expect(preview(page).getByTestId('task-preview-body')).toContainText('Mô tả tổng hợp')
  await expect(preview(page).getByTestId('task-preview-checklist')).toContainText('1/2 đã xong')
  await expect(preview(page).getByTestId('task-preview-item')).toHaveCount(2)
  await expect(preview(page)).not.toContainText('Chuẩn bị bản xem trước lịch tháng 10')
  await expect(preview(page)).not.toContainText('Nhấp')
  await expect(preview(page).getByRole('checkbox')).toHaveCount(0)
  expect(await preview(page).evaluate(node => getComputedStyle(node).backgroundColor)).toBe('rgb(255, 255, 255)')
  const getCount = previewApi.requests.length
  await page.keyboard.press('Escape')
  await title.focus()
  await expect(preview(page)).toBeVisible()
  expect(previewApi.requests.length).toBe(getCount)
  await shot(page, 'task-title-desktop')
  await title.press('Enter')
  await expect(page.getByTestId('task-detail-dialog')).toBeVisible()
  await expect(preview(page)).toHaveCount(0)
  await page.keyboard.press('Escape')
  await calendar(page)
  const chipTitle = chip(page).getByTestId('calendar-task-title')
  await chipTitle.hover()
  await expect(preview(page).getByTestId('task-preview-body')).toContainText('Mô tả tổng hợp')
  await expect(preview(page).getByTestId('task-preview-checklist')).toContainText('1/2 đã xong')
  await shot(page, 'calendar-chip-desktop')
  await page.keyboard.press('Escape')
  await chipTitle.focus()
  await expect(preview(page)).toBeVisible()
  await chipTitle.press('Enter')
  await expect(page.getByTestId('calendar-day-dialog')).toBeVisible()
  await expect(preview(page)).toHaveCount(0)
  await page.getByTestId('calendar-day-task-edit-trigger').first().click()
  await expect(page.getByRole('button', { name: 'Lưu thay đổi', exact: true })).toBeVisible()
})

test('task and calendar completion controls remain independent; drag keeps reschedule payload and closes preview', async ({ page, previewApi }, info) => {
  test.skip(info.project.name !== 'desktop', 'Desktop drag/checkbox path.')
  await page.goto('/')
  await card(page).getByTestId('task-title').hover()
  await card(page).getByTestId('task-checkbox').first().click()
  await expect(page.getByTestId('task-detail-dialog')).toHaveCount(0)
  await expect.poll(() => previewApi.writes.at(-1)).toMatchObject({ status: 'completed' })
  await calendar(page)
  await chip(page).getByTestId('calendar-chip-task-toggle').click()
  await expect(page.getByTestId('calendar-day-dialog')).toHaveCount(0)
  await expect.poll(() => previewApi.writes.at(-1)).toMatchObject({ status: 'open' })
  await chip(page).getByTestId('calendar-task-title').hover()
  await expect(preview(page)).toBeVisible()
  const payload = await chip(page).evaluate(node => {
    const dataTransfer = new DataTransfer()
    node.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer }))
    return dataTransfer.getData('application/json')
  })
  expect(JSON.parse(payload)).toEqual({ kind: 'reschedule-task', taskId, fromDay: '2026-10-20' })
  await expect(preview(page)).toHaveCount(0)
  await chip(page).dispatchEvent('dragend')
  const target = day(page, '2026-10-21')
  await page.evaluate(() => {
    const root = window as unknown as { previewDragTrace: unknown[] }
    root.previewDragTrace = []
    for (const type of ['dragstart', 'dragover', 'drop', 'dragend']) document.addEventListener(type, event => {
      const drag = event as DragEvent
      root.previewDragTrace.push({ type, target: (event.target as Element).closest('[data-day]')?.getAttribute('data-day'), allowed: drag.dataTransfer?.effectAllowed, drop: drag.dataTransfer?.dropEffect })
    })
  })
  await chip(page).dragTo(target)
  await info.attach('native-drag-trace', { body: JSON.stringify(await page.evaluate(() => (window as unknown as { previewDragTrace: unknown[] }).previewDragTrace)), contentType: 'application/json' })
  await expect.poll(() => previewApi.writes.some(write => (write as { due_on?: string }).due_on === '2026-10-21')).toBe(true)
  const trace = await page.evaluate(() => (window as unknown as { previewDragTrace: Array<{ type: string; drop?: string }> }).previewDragTrace)
  expect(trace.some(event => event.type === 'drop' && event.drop === 'move')).toBe(true)
  await page.getByTestId('calendar-quick-task-input').fill('Synthetic quick copy')
  await page.getByTestId('calendar-quick-task-draggable').dragTo(day(page, '2026-10-22'))
  await expect.poll(() => previewApi.requests.some(request => request === 'POST /api/tasks')).toBe(true)
  const copyTrace = await page.evaluate(() => (window as unknown as { previewDragTrace: Array<{ type: string; drop?: string }> }).previewDragTrace)
  expect(copyTrace.some(event => event.type === 'drop' && event.drop === 'copy')).toBe(true)
  await info.attach('native-copy-drag-trace', { body: JSON.stringify(copyTrace), contentType: 'application/json' })
})

test('long text and full checklist scroll without truncation; empty sections omitted and metadata uses VN precision', async ({ page, previewApi }, info) => {
  test.skip(info.project.name !== 'desktop', 'Full previews use desktop hover/focus; mobile full paths checked separately.')
  Object.assign(previewApi.tasks[0], { body_md: LONG, items: Array.from({ length: 35 }, (_, index) => ({ id: `long-${index}`, content: index === 34 ? 'Mục cuối đầy đủ' : `Mục ${index} ${'N'.repeat(75)}`, is_completed: index < 7, position: index })), due_precision: 'datetime', due_on: null, due_at: '2026-10-19T17:30:00Z' })
  await page.goto('/')
  await card(page).getByTestId('task-title').hover()
  await expect(preview(page).getByTestId('task-preview-item')).toHaveCount(35)
  await expect(preview(page).getByTestId('task-preview-body')).toContainText(LONG)
  await expect(preview(page).getByTestId('task-preview-metadata')).toContainText('00:30')
  expect(await fits(preview(page))).toBe(true)
  const sizes = await preview(page).locator('p,span').evaluateAll(nodes => nodes.map(node => parseFloat(getComputedStyle(node).fontSize)))
  expect(Math.min(...sizes)).toBeGreaterThanOrEqual(12)
  await preview(page).hover()
  await preview(page).getByTestId('task-preview-scroll').evaluate(node => { node.scrollTop = node.scrollHeight })
  await expect(preview(page).getByText('Mục cuối đầy đủ')).toBeInViewport()
  await shot(page, 'task-long-scroll-desktop')
  await page.keyboard.press('Escape')
  await calendar(page)
  await chip(page).getByTestId('calendar-task-title').focus()
  await expect(preview(page).getByTestId('task-preview-item')).toHaveCount(35)
  expect(await fits(preview(page))).toBe(true)
  await shot(page, 'calendar-long-desktop')
})

test('locked/private or removed source cannot retain an open preview', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop', 'Hover privacy contract.')
  await page.goto('/')
  await card(page, 'preview-private').getByTestId('task-title').focus()
  await expect(preview(page)).toContainText('Nội dung private synthetic')
  await page.getByTestId('private-lock-now').click()
  await expect(preview(page)).toHaveCount(0)
  await expect(card(page, 'preview-private')).toHaveCount(0)
  await calendar(page)
  await expect(day(page).getByText('Task riêng tư synthetic')).toHaveCount(0)
})

test('calendar private preview is removed on lock, including its cached body and checklist', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop', 'Desktop hover privacy contract.')
  await page.goto('/')
  await calendar(page)
  await day(page).getByTestId('calendar-task-title').filter({ hasText: 'Task riêng tư synthetic' }).focus()
  await expect(preview(page)).toContainText('Nội dung private synthetic')
  await page.getByTestId('private-lock-now').click()
  await expect(preview(page)).toHaveCount(0)
  await expect(day(page).getByText('Task riêng tư synthetic')).toHaveCount(0)
})

test('locked Task projection rejects cached private rows and keeps public previews usable', async ({ page, previewApi }, info) => {
  test.skip(info.project.name !== 'desktop', 'Cached-row privacy and hover regression.')
  await page.route('**/api/tasks/timeline?*', route => route.fulfill({ json: {
    items: previewApi.tasks, next_cursor: null,
    bucket_cursors: { dated: null, overdue: null, undated: null },
    has_previous: false, has_next: false,
    loaded_range_start: '2026-10-17', loaded_range_end: '2026-10-23',
  } }))
  await page.goto('/')
  await card(page, 'preview-private').getByTestId('task-title').hover()
  await expect(preview(page)).toContainText('Nội dung private synthetic')
  await page.getByTestId('private-lock-now').click()
  await expect(card(page, 'preview-private')).toHaveCount(0)
  await expect(preview(page)).toHaveCount(0)
  await card(page).getByTestId('task-title').hover()
  await expect(preview(page)).toContainText('Mô tả tổng hợp')
  await page.reload()
  await expect(card(page)).toBeVisible()
  await expect(card(page, 'preview-private')).toHaveCount(0)
})

test('mobile title/chip keeps full-detail/edit path and no horizontal overflow', async ({ page }, info) => {
  test.skip(info.project.name !== 'mobile', 'Touch route.')
  await page.goto('/')
  await card(page).getByTestId('task-title').tap()
  await expect(page.getByTestId('task-detail-dialog')).toBeVisible()
  await expect(page.getByTestId('task-detail-dialog')).toContainText('Mô tả tổng hợp')
  expect(await fits(page.getByTestId('task-detail-dialog'))).toBe(true)
  await shot(page, 'task-full-mobile')
  await page.keyboard.press('Escape')
  await calendar(page)
  await chip(page).tap()
  await expect(page.getByTestId('calendar-day-dialog')).toBeVisible()
  await page.getByTestId('calendar-day-task-edit-trigger').first().tap()
  await expect(page.getByRole('button', { name: 'Lưu thay đổi', exact: true })).toBeVisible()
  await shot(page, 'calendar-edit-mobile')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('empty metadata-only preview avoids empty body/checklist; historical paged calendar preserves full content', async ({ page, previewApi }, info) => {
  test.skip(info.project.name !== 'desktop', 'Desktop preview oracle.')
  Object.assign(previewApi.tasks[0], { body_md: ' ', items: [] })
  previewApi.tasks.push(task('historical', { title: 'Task lịch sử còn đủ nội dung', body_md: 'Nội dung lịch sử không bị cắt', due_on: '2026-09-20', pinned: false }))
  await page.goto('/')
  await card(page).getByTestId('task-title').hover()
  await expect(preview(page).getByTestId('task-preview-body')).toHaveCount(0)
  await expect(preview(page).getByTestId('task-preview-checklist')).toHaveCount(0)
  await expect(preview(page).getByTestId('task-preview-metadata')).toContainText('20/10/2026')
  await calendar(page)
  const historyDay = day(page, '2026-09-20')
  await historyDay.scrollIntoViewIfNeeded()
  await historyDay.getByTestId('calendar-task-title').filter({ hasText: 'Task lịch sử' }).hover()
  await expect(preview(page)).toContainText('Nội dung lịch sử không bị cắt')
  await expect(preview(page).getByTestId('task-preview-item')).toHaveCount(2)
  expect(previewApi.requests.some(request => request.includes('cursor=synthetic-page-2'))).toBe(true)
})
