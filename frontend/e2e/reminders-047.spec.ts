import { test, expect } from './fixtures/tasks'
import type { Reminder, ReminderSourceInfo } from '../src/reminder-ui'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/tracker/trackers**', (route) => route.fulfill({ json: { items: [] } }))
})

async function readOutboxRow(page: import('@playwright/test').Page, operationKind: string, entityId: string) {
  return page.evaluate(({ operationKind, entityId }) => new Promise<Record<string, unknown> | null>((resolve, reject) => {
    const opening = indexedDB.open('microsched-outbox')
    opening.onerror = () => reject(opening.error)
    opening.onsuccess = () => {
      const db = opening.result
      const request = db.transaction('outbox').objectStore('outbox').getAll()
      request.onerror = () => { db.close(); reject(request.error) }
      request.onsuccess = () => {
        const row = (request.result as Array<Record<string, unknown>>).find((item) =>
          item.operation_kind === operationKind && item.entity_id === entityId)
        db.close()
        resolve(row ?? null)
      }
    }
  }), { operationKind, entityId })
}

test('custom and relative editing previews the resolved instant and only submits one occurrence', async ({ page, taskApi }) => {
  const task = taskApi.tasks[0]
  const source: ReminderSourceInfo = { title: task.title, is_private: false, open: true,
    anchor_at: '2030-01-03T03:00:00Z', anchor_day: null, date_only: false }
  const existingReminderId = '2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f4301'
  let row: Reminder = { id: existingReminderId, source_id: task.id, source_kind: 'task', source_title: task.title,
    is_private: false, source_open: true, mode: 'absolute', due_at: '2030-01-02T13:00:00Z',
    offset_minutes: null, anchor_time: null, status: 'pending', revision: 1, attempt_count: 0, sent_at: null }
  const writes: Record<string, unknown>[] = []
  const refreshed: Array<{ id: string; mode: string; revision: number }> = []
  await page.route('**/api/reminders**', async (route) => {
    const request = route.request()
    if (request.url().includes('/source/')) return route.fulfill({ json: source })
    if (request.method() === 'PUT') {
      const payload = request.postDataJSON()
      writes.push(payload)
      row = { ...row, ...payload, id: String(payload.id), revision: row.revision + 1 }
      return route.fulfill({ json: row })
    }
    if (writes.length) refreshed.push({ id: row.id, mode: row.mode, revision: row.revision })
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
  await expect.poll(() => writes.length).toBe(1)
  await expect.poll(() => refreshed.some((snapshot) => snapshot.mode === 'relative' && snapshot.revision === 2)).toBe(true)
  expect(writes[0]).toMatchObject({ mode: 'relative', offset_minutes: -60,
    expected_id: existingReminderId, expected_revision: 1 })
  expect(String(writes[0].id)).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i)
  expect(row.id).toBe(writes[0].id)
  expect(refreshed).toContainEqual({ id: writes[0].id, mode: 'relative', revision: 2 })
  await expect.poll(async () => readOutboxRow(page, 'reminder.save', String(writes[0].id))).toBeNull()
})

test('undated reminder retains its immutable command through 503 and keeps the draft until actual ACK', async ({ page, taskApi }) => {
  const source: ReminderSourceInfo = { title: taskApi.tasks[0].title, is_private: false, open: true,
    anchor_at: null, anchor_day: null, date_only: false }
  const writes: Record<string, unknown>[] = []
  const refreshed: Array<{ id: string; mode: string; revision: number }> = []
  let row: Reminder | null = null
  let releaseSecond: (() => void) | undefined
  await page.route('**/api/reminders**', async (route) => {
    if (route.request().url().includes('/source/')) return route.fulfill({ json: source })
    if (route.request().method() === 'PUT') {
      const payload = route.request().postDataJSON() as Record<string, unknown>
      writes.push(payload)
      if (writes.length === 1) {
        return route.fulfill({ status: 503, json: { detail: 'Synthetic retryable failure' } })
      }
      await new Promise<void>((resolve) => { releaseSecond = resolve })
      row = { id: String(payload.id), source_id: taskApi.tasks[0].id, source_kind: 'task',
        source_title: source.title, is_private: false, source_open: true, mode: 'absolute',
        due_at: String(payload.due_at), offset_minutes: null, anchor_time: null, status: 'pending',
        revision: 1, attempt_count: 0, sent_at: null }
      return route.fulfill({ json: row })
    }
    if (row) refreshed.push({ id: row.id, mode: row.mode, revision: row.revision })
    return route.fulfill({ json: { items: row ? [row] : [], has_more: false } })
  })
  await page.goto('/')
  await page.locator(`[data-task-id="${taskApi.tasks[0].id}"]`).first().getByTestId('task-title').click()
  await page.getByTestId('task-detail-dialog').getByTestId('source-reminder').click()
  const editor = page.getByTestId('reminder-editor')
  await editor.getByRole('button', { name: 'Bật nhắc nhở', exact: true }).click()
  await editor.getByTestId('reminder-absolute').fill('2030-01-02T20:00')
  await expect(editor.getByTestId('reminder-preview')).toContainText('20:00')
  await editor.getByTestId('reminder-save').click()
  await expect.poll(() => writes.length).toBe(1)
  const commandId = String(writes[0]?.id)
  let retained: Record<string, unknown> | null = null
  await expect.poll(async () => {
    retained = await readOutboxRow(page, 'reminder.save', commandId)
    return retained?.state
  }).toBe('outcome_unknown')
  expect(retained).toMatchObject({ attempts: 1, body: { id: commandId, due_at: expect.any(String), expected_id: null, expected_revision: null }, payload_sha256: expect.any(String) })
  await expect(editor).toBeVisible()
  await expect(editor.getByTestId('reminder-outbox-pending')).toBeVisible()

  await expect.poll(() => writes.length, { timeout: 8_000 }).toBe(2)
  expect(writes[1]).toEqual(writes[0])
  let replayed: Record<string, unknown> | null = null
  await expect.poll(async () => {
    replayed = await readOutboxRow(page, 'reminder.save', commandId)
    return replayed?.attempts
  }).toBe(2)
  expect(replayed?.payload_sha256).toBe(retained?.payload_sha256)
  releaseSecond?.()
  await expect.poll(() => refreshed.some((snapshot) => snapshot.id === commandId && snapshot.revision === 1)).toBe(true)
  await expect.poll(async () => readOutboxRow(page, 'reminder.save', commandId)).toBeNull()
  await expect(editor.getByTestId('reminder-outbox-pending')).toHaveCount(0)
  expect(row?.id).toBe(commandId)
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
