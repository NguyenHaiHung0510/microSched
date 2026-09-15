import { expect } from '@playwright/test'

import { test } from './fixtures/tasks'
import type { MimiConversation } from '../src/mimi-api'

const conversationId = '01990000-0000-7000-8000-000000000056'
const runId = '01990000-0000-7000-8000-000000000057'
const changeSetId = '01990000-0000-7000-8000-000000000058'
const receiptId = '01990000-0000-7000-8000-000000000059'
const taskId = '01990000-0000-7000-8000-000000000060'

function emptyConversation(): MimiConversation {
  return {
    id: conversationId,
    sensitivity: 'standard',
    generation: 1,
    messages: [],
    runs: [],
    change_sets: [],
    receipts: [],
    events: [],
    feedback: [],
  }
}

test('Mimi preview-confirm-receipt-feedback stays usable without horizontal overflow', async ({
  page,
}) => {
  let conversation: MimiConversation | null = null
  await page.route('**/api/me', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        email: 'synthetic@example.test',
        signed_in_at: '2026-09-15T00:00:00Z',
        expires_at: '2026-09-16T00:00:00Z',
        private_until: null,
        private_locked_until: null,
        pin_is_set: true,
        pin_is_bootstrap: false,
        mimi_available: true,
      }),
    })
  })
  await page.route('**/api/mimi/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (request.method() === 'GET' && path.endsWith('/conversations/current')) {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(conversation) })
      return
    }
    expect(request.headers()['x-mimi-csrf']).toBe('1')
    if (request.method() === 'POST' && path.endsWith('/conversations')) {
      conversation = emptyConversation()
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(conversation) })
      return
    }
    if (request.method() === 'POST' && path.endsWith('/messages')) {
      const content = request.postDataJSON().content
      conversation = {
        ...emptyConversation(),
        generation: 2,
        messages: [
          { id: 'message-1', run_id: runId, client_id: 'client-1', sequence: 1, role: 'user', content, created_at: '2026-09-15T01:00:00Z' },
          { id: 'message-2', run_id: runId, client_id: null, sequence: 2, role: 'assistant', content: 'Mình đã đóng băng một preview tạo Task.', created_at: '2026-09-15T01:00:01Z' },
        ],
        runs: [{ id: runId, generation: 1, state: 'waiting_confirmation', provider_outcome: 'succeeded', deadline: '2026-09-15T01:02:00Z', error_code: null, created_at: '2026-09-15T01:00:00Z', completed_at: null }],
        change_sets: [{
          id: changeSetId,
          run_id: runId,
          state: 'pending',
          digest: 'a'.repeat(64),
          nonce: '01990000-0000-7000-8000-000000000061',
          expires_at: '2026-09-15T01:15:00Z',
          policy_version: 'mimi-standard-task-create.v1',
          operation: {
            operation_id: '01990000-0000-7000-8000-000000000062',
            tool: 'task.create.v1',
            args: { id: taskId, title: 'Chuẩn bị demo Mimi', body_md: null, status: 'open', priority: null, due_precision: 'none', due_on: null, due_at: null, is_private: false, items: [] },
          },
        }],
        receipts: [],
        events: [{ id: 'event-1', run_id: runId, sequence: 1, kind: 'run.accepted', payload: {}, created_at: '2026-09-15T01:00:00Z' }],
        feedback: [],
      }
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(conversation) })
      return
    }
    if (request.method() === 'POST' && path.endsWith('/decision')) {
      const receipt = { id: receiptId, change_set_id: changeSetId, operation_id: conversation!.change_sets[0].operation.operation_id, task_id: taskId, digest: 'a'.repeat(64), result: { task_id: taskId }, executed_at: '2026-09-15T01:01:00Z' }
      conversation = {
        ...conversation!,
        runs: conversation!.runs.map((run) => ({ ...run, state: 'completed', completed_at: '2026-09-15T01:01:00Z' })),
        change_sets: conversation!.change_sets.map((item) => ({ ...item, state: 'executed' })),
        receipts: [receipt],
      }
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(receipt) })
      return
    }
    if (request.method() === 'POST' && path.endsWith('/feedback')) {
      const feedback = { id: 'feedback-1', client_id: 'feedback-client', target_type: 'receipt', target_id: receiptId, state: 'new', unresolved: true, created_at: '2026-09-15T01:02:00Z' }
      conversation = { ...conversation!, feedback: [feedback] }
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(feedback) })
      return
    }
    await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
  })

  await page.goto('/')
  await page.getByRole('tab', { name: 'Mimi' }).click()
  await page.getByRole('button', { name: 'Bắt đầu conversation STANDARD' }).click()
  await expect(page.getByLabel('Nhắn Mimi')).toBeVisible()
  await page.getByLabel('Nhắn Mimi').fill('Tạo task Chuẩn bị demo Mimi')
  await page.getByRole('button', { name: 'Gửi' }).click()
  await expect(page.getByTestId('mimi-change-set')).toContainText('Chuẩn bị demo Mimi')

  const confirm = page.getByRole('button', { name: 'Xác nhận tạo Task' })
  const confirmBox = await confirm.boundingBox()
  expect(confirmBox).not.toBeNull()
  expect(confirmBox!.height).toBeGreaterThanOrEqual(44)
  await confirm.click()
  await expect(page.getByTestId('mimi-receipt')).toContainText(receiptId)

  await page.getByLabel('Feedback về kết quả này').fill('Preview cần hiển thị nguồn rõ hơn')
  await page.getByRole('button', { name: 'Lưu feedback' }).click()
  await expect(page.getByText('Feedback đã lưu · còn mở để xử lý.')).toBeVisible()

  const overflow = await page.evaluate(() => {
    const root = document.scrollingElement ?? document.documentElement
    return [root.scrollWidth, root.clientWidth]
  })
  expect(overflow[0]).toBeLessThanOrEqual(overflow[1])
})
