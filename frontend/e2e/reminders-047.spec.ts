import { test, expect } from './fixtures/tasks'
import type { Reminder, ReminderSourceInfo } from '../src/reminder-ui'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/tracker/trackers**', (route) => route.fulfill({ json: { items: [] } }))
})

test('custom and relative editing previews the resolved instant and only submits one occurrence', async ({ page, taskApi }) => {
  const task = taskApi.tasks[0]
  const source: ReminderSourceInfo = { title: task.title, is_private: false, open: true,
    anchor_at: '2030-01-03T03:00:00Z', anchor_day: null, date_only: false }
  let row: Reminder = { id: 'one-shot-047', source_id: task.id, source_kind: 'task', source_title: task.title,
    is_private: false, source_open: true, mode: 'absolute', due_at: '2030-01-02T13:00:00Z',
    offset_minutes: null, anchor_time: null, status: 'pending', revision: 1, attempt_count: 0, sent_at: null }
  const writes: Record<string, unknown>[] = []
  await page.route('**/api/reminders**', async (route) => {
    const request = route.request()
    if (request.url().includes('/source/')) return route.fulfill({ json: source })
    if (request.method() === 'PUT') {
      const payload = request.postDataJSON()
      writes.push(payload)
      row = { ...row, ...payload, revision: row.revision + 1 }
      return route.fulfill({ json: row })
    }
    return route.fulfill({ json: { items: [row], has_more: false } })
  })
  await page.goto('/')
  await page.getByTestId('reminder-center-open').click()
  await page.getByRole('button', { name: 'Sửa / tắt nhắc' }).click()
  const editor = page.getByTestId('reminder-editor')
  await editor.getByRole('combobox', { name: 'Cách đặt' }).click()
  await page.getByRole('option', { name: 'Trước / sau mốc đã lưu' }).click()
  await editor.getByRole('button', { name: '1 giờ trước', exact: true }).click()
  await expect(editor.getByTestId('reminder-preview')).toContainText('09:00')
  await editor.getByTestId('reminder-save').click()
  await expect(editor).toBeHidden()
  expect(writes).toHaveLength(1)
  expect(writes[0]).toMatchObject({ mode: 'relative', offset_minutes: -60,
    expected_id: 'one-shot-047', expected_revision: 1 })
})

test('undated source allows custom time and server errors remain visible with the draft', async ({ page, taskApi }) => {
  const source: ReminderSourceInfo = { title: taskApi.tasks[0].title, is_private: false, open: true,
    anchor_at: null, anchor_day: null, date_only: false }
  await page.route('**/api/reminders**', async (route) => {
    if (route.request().url().includes('/source/')) return route.fulfill({ json: source })
    if (route.request().method() === 'PUT') return route.fulfill({ status: 503, json: { detail: 'Chưa lưu được. Thử lại.' } })
    return route.fulfill({ json: { items: [], has_more: false } })
  })
  await page.goto('/')
  await page.locator(`[data-task-id="${taskApi.tasks[0].id}"]`).first().getByTestId('task-title').click()
  await page.getByTestId('task-detail-dialog').getByTestId('source-reminder').click()
  const editor = page.getByTestId('reminder-editor')
  await editor.getByRole('button', { name: 'Bật nhắc nhở', exact: true }).click()
  await editor.getByTestId('reminder-absolute').fill('2030-01-02T20:00')
  await expect(editor.getByTestId('reminder-preview')).toContainText('20:00')
  await editor.getByTestId('reminder-save').click()
  await expect(editor.getByRole('alert')).toContainText('Chưa lưu được')
  await expect(editor.getByTestId('reminder-absolute')).toHaveValue('2030-01-02T20:00')
})

test('private reminder center and editor state are removed on lock', async ({ page, taskApi }) => {
  const sentinel = 'Lời nhắc private giả lập 047'
  await page.route('**/api/reminders**', (route) => route.fulfill({ json: { items: taskApi.privateUntil ? [{
    id: 'private-047', source_id: taskApi.tasks[0].id, source_kind: 'task', source_title: sentinel,
    is_private: true, source_open: true, mode: 'absolute', due_at: '2030-01-02T13:00:00Z',
    status: 'pending', revision: 1, attempt_count: 0, offset_minutes: null, anchor_time: null, sent_at: null,
  }] : [], has_more: false } }))
  await page.goto('/')
  await page.getByTestId('reminder-center-open').click()
  await expect(page.getByTestId('reminder-center')).toContainText(sentinel)
  await page.getByTestId('reminder-center').getByRole('button', { name: 'Đóng', exact: true }).click()
  await page.getByTestId('private-lock-now').click()
  await page.getByTestId('reminder-center-open').click()
  await expect(page.getByTestId('reminder-center')).not.toContainText(sentinel)
  await expect(page.getByTestId('reminder-center')).toContainText('Không có lời nhắc')
})

test('date-only relative reminder requires an explicit anchor clock', async ({ page, taskApi }) => {
  const title = taskApi.tasks[0].title
  await page.route('**/api/reminders**', (route) => route.fulfill({ json:
    route.request().url().includes('/source/') ? { title, is_private: false, open: true,
      anchor_at: null, anchor_day: '2030-01-03', date_only: true }
      : { items: [{ id: 'day-047', source_kind: 'task', source_id: taskApi.tasks[0].id, source_title: title,
        is_private: false, source_open: true, mode: 'absolute', status: 'pending', revision: 1,
        due_at: '2030-01-02T13:00:00Z' }], has_more: false } }))
  await page.goto('/')
  await page.getByTestId('reminder-center-open').click()
  await page.getByRole('button', { name: 'Sửa / tắt nhắc' }).click()
  const editor = page.getByTestId('reminder-editor')
  await editor.getByRole('combobox', { name: 'Cách đặt' }).click()
  await page.getByRole('option', { name: 'Trước / sau mốc đã lưu' }).click()
  await expect(editor.getByTestId('reminder-save')).toBeDisabled()
  await editor.getByLabel('Giờ mốc trong ngày').fill('09:00')
  await editor.getByRole('button', { name: '1 giờ trước', exact: true }).click()
  await expect(editor.getByTestId('reminder-preview')).toContainText('08:00')
})
