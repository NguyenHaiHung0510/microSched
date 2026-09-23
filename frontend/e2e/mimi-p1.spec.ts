import { expect } from '@playwright/test'

import { test } from './fixtures/tasks'
import type { MimiConversation } from '../src/mimi-api'

const capturePreview = process.env.CAPTURE_MIMI_PREVIEW === '1'

const conversationId = '01990000-0000-7000-8000-000000000056'
const runId = '01990000-0000-7000-8000-000000000057'
const changeSetId = '01990000-0000-7000-8000-000000000058'
const receiptId = '01990000-0000-7000-8000-000000000059'
const taskId = '01990000-0000-7000-8000-000000000060'

function emptyConversation(): MimiConversation {
  return {
    id: conversationId,
    sensitivity: 'standard',
    title: 'Hội thoại Mimi · 15/09 08:00',
    title_source: 'auto',
    title_locked: false,
    generation: 1,
    metadata_version: 1,
    archived_at: null,
    updated_at: '2026-09-15T01:00:00Z',
    messages: [],
    runs: [],
    change_sets: [],
    receipts: [],
    events: [],
    feedback: [],
  }
}

function summary(conversation: MimiConversation) {
  return {
    id: conversation.id,
    sensitivity: conversation.sensitivity,
    title: conversation.title ?? 'Hội thoại Mimi',
    title_source: conversation.title_source ?? 'auto',
    title_locked: conversation.title_locked ?? false,
    generation: conversation.generation,
    metadata_version: conversation.metadata_version ?? 1,
    archived_at: conversation.archived_at ?? null,
    updated_at: conversation.updated_at ?? '2026-09-15T01:00:00Z',
    latest_run_state: conversation.runs.at(-1)?.state ?? null,
  }
}

test('Mimi Control Center and shared thread keep preview-confirm-receipt usable', async ({
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
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(conversation?.archived_at ? null : conversation) })
      return
    }
    if (request.method() === 'GET' && path.endsWith('/conversations')) {
      const state = new URL(request.url()).searchParams.get('state') ?? 'active'
      const visible = conversation && ((state === 'archived') === Boolean(conversation.archived_at))
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: visible ? [summary(conversation)] : [], next_cursor: null }) })
      return
    }
    if (request.method() === 'GET' && path.endsWith(`/conversations/${conversationId}`)) {
      await route.fulfill({ status: conversation ? 200 : 404, contentType: 'application/json', body: JSON.stringify(conversation ?? {}) })
      return
    }
    if (request.method() === 'GET' && path.endsWith('/preview')) {
      await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
      return
    }
    expect(request.headers()['x-mimi-csrf']).toBe('1')
    if (request.method() === 'POST' && path.endsWith('/conversations')) {
      conversation = emptyConversation()
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(summary(conversation)) })
      return
    }
    if (request.method() === 'PATCH' && path.endsWith(`/conversations/${conversationId}`)) {
      const title = request.postDataJSON().title
      conversation = { ...conversation!, title, title_source: 'owner', title_locked: true, metadata_version: (conversation!.metadata_version ?? 1) + 1 }
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(summary(conversation)) })
      return
    }
    if (request.method() === 'POST' && path.endsWith(`/conversations/${conversationId}/archive`)) {
      conversation = { ...conversation!, archived_at: '2026-09-15T01:03:00Z', metadata_version: (conversation!.metadata_version ?? 1) + 1 }
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(summary(conversation)) })
      return
    }
    if (request.method() === 'POST' && path.endsWith(`/conversations/${conversationId}/restore`)) {
      conversation = { ...conversation!, archived_at: null, metadata_version: (conversation!.metadata_version ?? 1) + 1 }
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(summary(conversation)) })
      return
    }
    if (request.method() === 'POST' && path.endsWith('/messages/stream')) {
      const content = request.postDataJSON().content
      conversation = {
        ...conversation!,
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
      const stream = [
        `event: run.reserved\ndata: ${JSON.stringify({ run_id: runId })}\n\n`,
        `event: provider.connected\ndata: ${JSON.stringify({ id: 'event-connected', run_id: runId, sequence: 2, kind: 'provider.connected', payload: { status: 200 }, created_at: '2026-09-15T01:00:00Z' })}\n\n`,
        `event: assistant.delta\ndata: ${JSON.stringify({ id: 'event-delta', run_id: runId, sequence: 3, kind: 'assistant.delta', payload: { text: 'Đang chuẩn bị preview…' }, created_at: '2026-09-15T01:00:01Z' })}\n\n`,
        `event: change_set.ready\ndata: ${JSON.stringify({ id: 'event-ready', run_id: runId, sequence: 4, kind: 'change_set.ready', payload: { change_set_id: changeSetId }, created_at: '2026-09-15T01:00:02Z' })}\n\n`,
        `event: conversation.snapshot\ndata: ${JSON.stringify(conversation)}\n\n`,
      ].join('')
      await route.fulfill({ contentType: 'text/event-stream', body: stream })
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
  await expect(page.getByRole('heading', { name: 'Mimi Control Center' })).toBeVisible()
  await expect(page.getByText('Route hiệu lực')).toBeVisible()
  if (capturePreview) {
    await page.screenshot({
      path: `test-results/task-058/control-center-${page.viewportSize()?.width ?? 'unknown'}.png`,
      fullPage: true,
    })
  }
  await page.getByRole('button', { name: 'Hội thoại' }).click()
  await page.getByRole('button', { name: 'Bắt đầu conversation STANDARD' }).click()
  await expect(page.getByLabel('Nhắn Mimi')).toBeVisible()
  await page.getByRole('button', { name: /^Tùy chọn / }).first().click()
  await page.getByRole('menuitem', { name: 'Đổi tên' }).click()
  await page.getByRole('textbox', { name: 'Tên hội thoại' }).fill('Tổng duyệt demo Mimi')
  await page.getByRole('button', { name: 'Lưu tên' }).click()
  await expect(page.getByText('Tổng duyệt demo Mimi').first()).toBeVisible()
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

  await page.getByRole('button', { name: /^Tùy chọn / }).first().click()
  await page.getByRole('menuitem', { name: 'Lưu trữ' }).click()
  await page.getByRole('button', { name: 'Đã lưu' }).click()
  await expect(page.getByText('Tổng duyệt demo Mimi').first()).toBeVisible()
  await page.getByRole('button', { name: /^Tùy chọn / }).first().click()
  await page.getByRole('menuitem', { name: 'Khôi phục' }).click()
  await page.getByRole('button', { name: 'Đang dùng' }).click()
  await expect(page.getByText('Tổng duyệt demo Mimi').first()).toBeVisible()

  const overflow = await page.evaluate(() => {
    const root = document.scrollingElement ?? document.documentElement
    return [root.scrollWidth, root.clientWidth]
  })
  expect(overflow[0]).toBeLessThanOrEqual(overflow[1])
})

test('Mimi side-chat stays available from the Task surface without page overflow', async ({
  page,
}) => {
  let conversation: MimiConversation | null = emptyConversation()
  await page.route('**/api/me', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        email: 'synthetic@example.test',
        signed_in_at: '2026-09-17T00:00:00Z',
        expires_at: '2026-09-18T00:00:00Z',
        private_until: null,
        private_locked_until: null,
        pin_is_set: true,
        pin_is_bootstrap: false,
        mimi_available: true,
      }),
    })
  })
  await page.route('**/api/mimi/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (route.request().method() === 'GET' && path.endsWith('/conversations/current')) {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(conversation) })
      return
    }
    await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
  })

  await page.goto('/')
  await expect(page.getByRole('tab', { name: 'Task' })).toHaveAttribute('aria-selected', 'true')
  await page.getByTestId('mimi-dock-toggle').click()
  await expect(page.getByTestId('mimi-side-chat')).toBeVisible()
  await expect(page.getByLabel('Nhắn Mimi')).toBeVisible()
  if (capturePreview) {
    await page.screenshot({
      path: `test-results/task-058/side-chat-${page.viewportSize()?.width ?? 'unknown'}.png`,
      fullPage: false,
    })
  }

  const overflow = await page.evaluate(() => {
    const root = document.scrollingElement ?? document.documentElement
    return [root.scrollWidth, root.clientWidth]
  })
  expect(overflow[0]).toBeLessThanOrEqual(overflow[1])

  conversation = null
})
