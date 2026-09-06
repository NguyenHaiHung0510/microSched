import { test, expect, type FixtureTracker } from './fixtures/tracker'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/subscriptions**', (route) => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/settings**', (route) => route.fulfill({ json: { items: [] } }))
})

test('private tasks use a label and edge on timeline and disappear after locking', async ({ page, taskApi }) => {
  const today = new Date(Date.now() + 7 * 3600_000).toISOString().slice(0, 10)
  taskApi.tasks = [false, true].map((isPrivate) => ({
    ...taskApi.tasks[0], id: isPrivate ? 'task-private-043' : 'task-standard-043',
    title: isPrivate ? 'Task riêng tư mô phỏng' : 'Task tiêu chuẩn mô phỏng',
    is_private: isPrivate, pinned: false, status: 'open' as const, due_precision: 'date' as const, due_on: today, due_at: null,
  }))
  await page.goto('/')
  const privateCard = page.locator('[data-testid="task-card"][data-task-id="task-private-043"]')
  const standard = page.locator('[data-testid="task-card"][data-task-id="task-standard-043"]')
  await expect(privateCard.getByTestId('private-marker')).toBeVisible()
  await expect(standard.getByTestId('private-marker')).toHaveCount(0)
  const contrast = await privateCard.getByTestId('private-marker').evaluate((element) => {
    const style = getComputedStyle(element)
    const context = document.createElement('canvas').getContext('2d')!
    const luminance = (color: string) => {
      context.clearRect(0, 0, 1, 1)
      context.fillStyle = color
      context.fillRect(0, 0, 1, 1)
      const channels = [...context.getImageData(0, 0, 1, 1).data].slice(0, 3).map((channel) => {
        const value = channel / 255
        return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
      })
      return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722
    }
    const foreground = luminance(style.color)
    const background = luminance(style.backgroundColor)
    return (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05)
  })
  expect(contrast).toBeGreaterThanOrEqual(4.5)
  expect(await privateCard.evaluate((node) => parseFloat(getComputedStyle(node).borderInlineStartWidth))).toBe(4)
  await page.getByTestId('private-lock-now').click()
  await expect(privateCard).toHaveCount(0)
  await expect(standard).toBeVisible()
})

test('calendar private task and annotation show markers in grid and full day detail', async ({ page, taskApi }) => {
  const today = new Date(Date.now() + 7 * 3600_000).toISOString().slice(0, 10)
  taskApi.tasks = [{ ...taskApi.tasks[0], id: 'calendar-private-043', title: 'Task lịch riêng tư mô phỏng', is_private: true, due_precision: 'date', due_on: today, due_at: null, status: 'open' }]
  await page.route('**/api/calendar/**', (route) => {
    const url = new URL(route.request().url())
    const annotations = taskApi.privateUntil ? [{ id: 'annotation-private-043', starts_on: today, ends_on: today, label: 'Dấu ngày riêng tư mô phỏng', note_md: null, color: 'rose', is_private: true, created_at: null, updated_at: null }] : []
    return route.fulfill({ json: { items: url.pathname.endsWith('/annotations') ? annotations : [] } })
  })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Lịch' }).click()
  const day = page.locator(`[data-testid="calendar-day-cell"][data-day="${today}"]`)
  await expect(day.locator('[data-testid="calendar-day-chip-task"][data-private="true"]')).toBeVisible()
  await expect(day.locator('[data-testid="calendar-day-annotation"][data-private="true"]')).toBeVisible()
  await day.click({ position: { x: 5, y: 5 } })
  await expect(page.getByTestId('calendar-day-dialog')).toBeVisible()
  await expect(page.getByTestId('calendar-day-task').getByTestId('private-marker')).toBeVisible()
  await expect(page.getByTestId('calendar-annotation-detail').getByTestId('private-marker')).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByTestId('private-lock-now').click()
  await expect(page.locator('[data-testid="calendar-day-chip-task"][data-private="true"]')).toHaveCount(0)
  await expect(page.locator('[data-testid="calendar-day-annotation"][data-private="true"]')).toHaveCount(0)
})

test('upcoming reminders keep the actual date, same-hour dates separate, and unknown dates explicit', async ({ page, trackerApi }) => {
  const template = trackerApi.trackers[0]
  trackerApi.trackers = [
    { ...template, id: 'cadence-five', name: 'Kiểm tra bản sao lưu mô phỏng', reminder_mode: 'fixed', reminder_interval_days: 5, reminder_time: '08:00:00', next_reminder_at: '2026-09-11T08:00:00+07:00' },
    { ...template, id: 'cadence-daily', name: 'Nhắc sinh hoạt mô phỏng', reminder_mode: 'fixed', reminder_interval_days: 1, reminder_time: '08:00:00', next_reminder_at: '2026-09-07T08:00:00+07:00' },
    { ...template, id: 'cadence-unknown', name: 'Chưa có lịch từ máy chủ', reminder_time: '09:00:00', next_reminder_at: null },
  ]
  await page.goto('/trackers')
  const groups = page.getByTestId('tracker-reminder-group')
  await expect(groups).toHaveCount(3)
  await expect(groups.nth(0).getByTestId('tracker-reminder-date')).toContainText('07/09/2026')
  await expect(groups.nth(1).getByTestId('tracker-reminder-date')).toContainText('11/09/2026')
  await expect(groups.nth(1).getByTestId('tracker-reminder-time')).toHaveText('08:00')
  await expect(groups.nth(1)).toContainText('Mỗi 5 ngày')
  await expect(groups.nth(2)).toHaveAttribute('data-next-at', '')
  await expect(groups.nth(2).getByTestId('tracker-reminder-date')).toHaveText('Chưa xác định ngày')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('private tracker has a label and edge while standard stays neutral, then disappears on lock', async ({ page, trackerApi, taskApi }) => {
  const template = trackerApi.trackers[0]
  const privateTracker: FixtureTracker = { ...template, id: 'private-043', name: 'Nhật ký riêng tư mô phỏng', is_private: true }
  trackerApi.trackers = [template, privateTracker]
  // Model the established server read gate; no real identities or sessions involved.
  await page.route('**/api/tracker/trackers', (route) => route.fulfill({ json: {
    items: trackerApi.trackers.filter((tracker) => !tracker.is_private || Boolean(taskApi.privateUntil)),
  } }))
  await page.goto('/trackers')
  const standard = page.getByTestId('tracker-card').filter({ has: page.getByTestId('tracker-button').filter({ hasText: template.name }) })
  const privateCard = page.getByTestId('tracker-card').filter({ has: page.locator('[data-testid="tracker-button"][data-tracker-id="private-043"]') })
  await expect(privateCard.getByTestId('private-marker')).toBeVisible()
  await expect(standard.getByTestId('private-marker')).toHaveCount(0)
  expect(await privateCard.evaluate((node) => parseFloat(getComputedStyle(node).borderInlineStartWidth))).toBe(4)
  await page.getByTestId('private-lock-now').click()
  await expect(privateCard).toHaveCount(0)
  await expect(page.getByTestId('tracker-card').filter({ hasText: template.name })).toBeVisible()
})

test('private note cards and details carry a visible label without changing standard notes', async ({ page, taskApi }) => {
  const notes = [false, true].map((isPrivate) => ({
    id: isPrivate ? 'private-note-043' : 'standard-note-043',
    title: isPrivate ? 'Ghi chú riêng tư mô phỏng' : 'Ghi chú tiêu chuẩn mô phỏng',
    body_md: 'Nội dung synthetic để kiểm tra nhãn và bố cục.',
    pinned: false, is_private: isPrivate, items: [], created_at: '2026-09-01T00:00:00Z', updated_at: null,
  }))
  await page.route('**/api/notes**', (route) => route.fulfill({ json: {
    items: notes.filter((note) => !note.is_private || Boolean(taskApi.privateUntil)),
  } }))
  await page.goto('/')
  await page.getByRole('tab', { name: 'Ghi chú' }).click()
  const privateCard = page.locator('[data-testid="note-card"][data-note-id="private-note-043"]')
  const standard = page.locator('[data-testid="note-card"][data-note-id="standard-note-043"]')
  await expect(privateCard.getByTestId('note-private-badge-card')).toBeVisible()
  await expect(standard.getByTestId('note-private-badge-card')).toHaveCount(0)
  expect(await privateCard.evaluate((node) => parseFloat(getComputedStyle(node).borderInlineStartWidth))).toBe(4)
  await privateCard.getByTestId('note-title').click()
  await expect(page.getByTestId('note-private-badge-detail')).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByTestId('private-lock-now').click()
  await expect(privateCard).toHaveCount(0)
  await expect(standard).toBeVisible()
})
