import type { Page } from '@playwright/test'
import { expect, test } from './fixtures/tasks'

const day = new Date(Date.now() + 7 * 3600000).toISOString().slice(0, 10)
const addDays = (value: string, delta: number) => new Date(Date.parse(value + 'T00:00:00Z') + delta * 86400000).toISOString().slice(0, 10)
const range = { id: '019a0e2e-0000-7000-8001-000000000099', starts_on: day.slice(0, 8) + '26', ends_on: day.slice(0, 8) + '28',
  label: 'Dấu khoảng synthetic', note_md: null, color: 'rose', is_private: false, created_at: null, updated_at: null }

async function calendar(page: Page) {
  const state = { annotation: { ...range }, writes: 0, rejectNext: false }
  await page.route('**/api/calendar/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (path === '/api/calendar/sources') return route.fulfill({ json: { items: [] } })
    if (path === '/api/calendar/events') return route.fulfill({ json: { items: [] } })
    if (path === '/api/calendar/annotations' && request.method() === 'GET') return route.fulfill({ json: { items: [state.annotation] } })
    if (path === '/api/calendar/annotations/' + range.id && request.method() === 'PATCH') {
      state.writes++
      if (state.rejectNext) { state.rejectNext = false; return route.fulfill({ status: 422, json: { detail: 'Ngày chưa hợp lệ trong phép thử.' } }) }
      state.annotation = { ...state.annotation, ...request.postDataJSON() }
      return route.fulfill({ json: state.annotation })
    }
    return route.fallback()
  })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Lịch', exact: true }).click()
  return state
}
const cell = (page: Page, value: string) => page.locator(`[data-testid="calendar-day-cell"][data-day="${value}"]`)

test('tap and keyboard move datetime Task and undo the full schedule', async ({ page, taskApi }, testInfo) => {
  const task = taskApi.tasks.find(item => !item.is_private)!
  const overdue = taskApi.tasks.find(item => !item.is_private && item.id !== task.id && item.status === 'open')!
  Object.assign(overdue, { title: 'Việc quá hạn synthetic', due_precision: 'date', due_on: addDays(day, -1), due_at: null })
  taskApi.tasks = [task, overdue]
  Object.assign(task, { title: 'Việc có giờ synthetic', due_precision: 'datetime', due_on: null, due_at: day + 'T23:30:45.123+07:00' })
  const original = task.due_at!
  await calendar(page)
  await cell(page, day).click()
  const move = page.getByTestId('calendar-task-move')
  await expect(move).toHaveAccessibleName('Chuyển ngày Việc có giờ synthetic')
  await expect(move).toHaveText('')
  await expect(move.locator('svg.lucide-calendar')).toHaveCount(1)
  const target = await move.boundingBox()
  expect(target!.width).toBeGreaterThanOrEqual(44)
  expect(target!.height).toBeGreaterThanOrEqual(44)
  await move.focus()
  await expect(move).toBeFocused()
  await expect(page.getByTestId('calendar-day-overdue-task-reschedule')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('day-detail-due-overdue-icon.png') })
  await move.click()
  await expect(page.getByRole('dialog')).toHaveCount(1)
  const dialog = page.getByTestId('calendar-move-dialog')
  await dialog.getByLabel('Ngày mới').fill(addDays(day, 3))
  await dialog.getByLabel('Ngày mới').press('Enter')
  await expect(dialog).toBeHidden()
  await expect.poll(() => Date.parse(task.due_at!)).toBe(Date.parse(addDays(day, 3) + 'T23:30:45.123+07:00'))
  expect(task.due_precision).toBe('datetime'); expect(task.due_on).toBeNull()
  await page.getByRole('button', { name: 'Hoàn tác', exact: true }).click()
  await expect.poll(() => Date.parse(task.due_at!)).toBe(Date.parse(original))
  expect(task.due_precision).toBe('datetime'); expect(task.due_on).toBeNull()
})

test('desktop Task drag retains datetime instead of flattening it to a date', async ({ page, taskApi, isMobile }) => {
  test.skip(isMobile, 'Mobile uses the tap/keyboard Chuyển ngày alternative')
  const task = taskApi.tasks.find(item => !item.is_private)!
  taskApi.tasks = [task]
  Object.assign(task, { due_precision: 'datetime', due_on: null, due_at: day + 'T09:30:12.345+07:00' })
  await calendar(page)
  await page.locator(`[data-testid="calendar-day-chip-task"][data-task-id="${task.id}"]`).dragTo(cell(page, addDays(day, 2)))
  await expect.poll(() => Date.parse(task.due_at!)).toBe(Date.parse(addDays(day, 2) + 'T09:30:12.345+07:00'))
  expect(task.due_precision).toBe('datetime'); expect(task.due_on).toBeNull()
})

test('middle-day range move keeps duration, canceled/empty input sends no request and rejected write keeps retry draft', async ({ page, taskApi }) => {
  taskApi.tasks = []
  const state = await calendar(page)
  const middle = day.slice(0, 8) + '27'
  const last = new Date(Date.UTC(Number(day.slice(0, 4)), Number(day.slice(5, 7)), 0)).toISOString().slice(0, 10)
  async function open() {
    await cell(page, middle).click()
    await page.getByTestId('calendar-annotation-move').click()
    await expect(page.getByRole('dialog')).toHaveCount(1)
  }
  await open()
  let dialog = page.getByTestId('calendar-move-dialog')
  await dialog.getByLabel('Chuyển ngày đã chọn tới').fill('')
  await dialog.getByRole('button', { name: 'Chuyển ngày', exact: true }).click()
  expect(state.writes).toBe(0)
  await dialog.getByRole('button', { name: 'Huỷ', exact: true }).click()
  await expect(cell(page, middle)).toBeFocused()
  expect(state.annotation).toEqual(range)
  await open(); dialog = page.getByTestId('calendar-move-dialog')
  await dialog.getByLabel('Chuyển ngày đã chọn tới').fill(last)
  await expect(dialog.getByTestId('calendar-move-preview')).toContainText('3 ngày')
  state.rejectNext = true
  await dialog.getByRole('button', { name: 'Chuyển ngày', exact: true }).click()
  await expect(dialog.getByTestId('calendar-move-error')).toContainText('Ngày chưa hợp lệ')
  await expect(dialog.getByLabel('Chuyển ngày đã chọn tới')).toHaveValue(last)
  expect(state.annotation).toEqual(range)
  await dialog.getByRole('button', { name: 'Chuyển ngày', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(state.annotation.starts_on).toBe(addDays(last, -1))
  expect(state.annotation.ends_on).toBe(addDays(last, 1))
  expect(state.writes).toBe(2)
  await page.getByRole('button', { name: 'Hoàn tác', exact: true }).click()
  await expect.poll(() => state.annotation.starts_on).toBe(range.starts_on)
  expect(state.annotation.ends_on).toBe(range.ends_on)
})
