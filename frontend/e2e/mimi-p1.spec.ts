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
    if (request.method() === 'GET' && path.endsWith('/capabilities')) {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({
        context_v1_enabled: false,
        live_provider_enabled: false,
        requested_model: null,
        requested_effort: null,
        route_mode: null,
        model_selection_enabled: false,
        context_limit: 131072,
        output_reserve: 4096,
        policy_id: null,
        policy_sha256: null,
      }) })
      return
    }
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

test('P1C-A synthetic browser loop keeps one conversation observable and composer reachable', async ({
  page,
}) => {
  let conversation: MimiConversation | null = null
  let messagePosts = 0
  let observerGets = 0
  const createdAt = '2026-09-23T02:00:00Z'
  const activeRun = {
    id: runId,
    generation: 1,
    state: 'running',
    provider_outcome: null,
    deadline: '2026-09-23T02:30:00Z',
    error_code: null,
    created_at: createdAt,
    completed_at: null,
  }
  const completedSnapshot = () => ({
    ...conversation!,
    runs: [{ ...activeRun, state: 'completed', provider_outcome: 'succeeded', completed_at: createdAt }],
    events: [
      {
        id: 'context-manifest', run_id: runId, sequence: 1, kind: 'context.manifest', created_at: createdAt,
        payload: {
          input_upper_bound: 1200,
          context_limit: 131072,
          checkpoint_frontier: 0,
          sources: [{ source_id: 'tasks.standard', coverage: 'bounded', count: 1, omitted_fields: ['body_md'], data_as_of: createdAt }],
        },
      },
    ],
    provider_calls: [{ run_id: runId, attempt: 1, state: 'completed', requested_model: 'synthetic-route', requested_effort: 'low', actual_model: 'synthetic-route', actual_provider: 'fake', usage: {} }],
  })

  await page.route('**/api/me', async (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      email: 'synthetic@example.test', signed_in_at: createdAt,
      expires_at: '2026-09-24T02:00:00Z', private_until: null, private_locked_until: null,
      pin_is_set: true, pin_is_bootstrap: false, mimi_available: true,
    }),
  }))
  await page.route('**/api/mimi/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (request.method() === 'GET' && path.endsWith('/capabilities')) {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({
        context_v1_enabled: true, live_provider_enabled: false, requested_model: 'synthetic-route',
        requested_effort: 'low', route_mode: 'fake', model_selection_enabled: false,
        context_limit: 131072, output_reserve: 4096, policy_id: 'synthetic-policy', policy_sha256: '0'.repeat(64),
      }) })
      return
    }
    if (request.method() === 'GET' && path.endsWith('/conversations/current')) {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(conversation) })
      return
    }
    if (request.method() === 'GET' && path.endsWith('/conversations')) {
      const items = conversation ? [summary(conversation)] : []
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items, next_cursor: null }) })
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
    if (request.method() === 'GET' && path.endsWith(`/runs/${runId}/events/stream`)) {
      observerGets += 1
      const snapshot = completedSnapshot()
      conversation = snapshot
      await route.fulfill({ contentType: 'text/event-stream', body: `event: conversation.snapshot\ndata: ${JSON.stringify(snapshot)}\n\n` })
      return
    }
    if (request.method() === 'POST' && path.endsWith('/conversations')) {
      conversation = emptyConversation()
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(summary(conversation)) })
      return
    }
    if (request.method() === 'POST' && path.endsWith('/messages/stream')) {
      messagePosts += 1
      const content = request.postDataJSON().content as string
      conversation = {
        ...conversation!,
        generation: conversation!.generation + 1,
        messages: [...conversation!.messages, {
          id: `user-${messagePosts}`, run_id: runId, client_id: 'synthetic-client',
          sequence: conversation!.messages.length + 1, role: 'user', content, created_at: createdAt,
        }],
        runs: [activeRun],
      }
      // The run is durably accepted, while this response ends before a terminal snapshot.
      // Reload must attach to the GET observer and must never repeat the message POST.
      await route.fulfill({ contentType: 'text/event-stream', body: `event: run.reserved\ndata: ${JSON.stringify({ run_id: runId })}\n\n` })
      return
    }
    await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
  })

  await page.route('**/api/tasks/timeline**', async (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [{
    id: 'task-synthetic', title: 'Task chỉ hiện trong rail', body_md: null, status: 'open', priority: null,
    due_precision: 'none', due_on: null, due_at: null, is_private: false, pinned: false,
    items: [], created_at: createdAt, updated_at: createdAt,
  }], counts: { overdue: 0, dated: 0, undated: 1 }, bucket_cursors: { overdue: null, dated: null, undated: null } }) }))
  await page.route('**/api/notes**', async (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [] }) }))
  await page.route('**/api/calendar/events**', async (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [] }) }))
  await page.route('**/api/tracker/trackers', async (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [] }) }))

  await page.goto('/')
  await page.getByRole('tab', { name: 'Mimi' }).click()
  await page.getByRole('button', { name: 'Hội thoại' }).click()
  await page.getByRole('button', { name: 'Cuộc trò chuyện mới' }).click()
  const composer = page.getByTestId('mimi-input')
  await expect(composer).toBeVisible()
  await composer.scrollIntoViewIfNeeded()
  const composerBox = await composer.boundingBox()
  expect(composerBox).not.toBeNull()
  expect(composerBox!.y + composerBox!.height).toBeLessThanOrEqual(page.viewportSize()!.height)

  await composer.fill('Dòng đầu')
  await composer.press('Shift+Enter')
  await composer.type('dòng hai')
  await expect(composer).toHaveValue('Dòng đầu\ndòng hai')
  await composer.press('Control+A')
  await composer.fill('Câu hỏi chỉ đọc')
  await composer.press('Enter')
  await expect.poll(() => messagePosts).toBe(1)

  const dockToggle = page.getByTestId('mimi-dock-toggle')
  await dockToggle.click()
  await expect(page.getByTestId('mimi-side-chat')).toBeVisible()
  await expect(page.getByTestId('mimi-side-chat').getByTestId('mimi-messages')).toContainText('Câu hỏi chỉ đọc')
  if ((page.viewportSize()?.width ?? 1280) < 640) await page.keyboard.press('Escape')
  else await dockToggle.click()
  await expect(page.getByTestId('mimi-side-chat')).toHaveCount(0)

  await page.getByRole('button', { name: 'Thu gọn danh sách' }).click()
  await expect(page.getByRole('heading', { name: 'Cuộc trò chuyện' })).toHaveCount(0)
  await page.getByRole('button', { name: /Hội thoại \(/ }).click()
  await expect(page.getByRole('button', { name: 'Thu gọn danh sách' })).toBeVisible()
  await page.getByRole('button', { name: 'Xem dữ liệu liên quan' }).click()
  await expect(page.getByTestId('mimi-context-rail')).toContainText('Task chỉ hiện trong rail')
  await expect(page.getByText('Bạn nhìn thấy ở rail không đồng nghĩa nội dung tự động được gửi cho model.')).toBeVisible()
  await page.getByRole('button', { name: 'Đóng dữ liệu' }).click()
  await expect(page.getByTestId('mimi-context-rail')).toHaveCount(0)

  // A standard browser viewport is enough: no fullscreen/F11 is used to reach the composer.
  await page.reload()
  await page.getByRole('tab', { name: 'Mimi' }).click()
  await page.getByRole('button', { name: 'Hội thoại' }).click()
  await expect(page.getByTestId('mimi-input')).toBeVisible()
  await expect.poll(() => observerGets).toBeGreaterThan(0)
  await page.getByRole('button', { name: 'Xem dữ liệu liên quan' }).click()
  await expect(page.getByTestId('mimi-context-rail')).toContainText('Task chỉ hiện trong rail')
  await page.getByRole('tab', { name: 'Run', exact: true }).click()
  const inspector = page.getByTestId('mimi-context-inspector')
  await inspector.locator('summary').click()
  await expect(inspector).toContainText('tasks.standard')
  await expect(inspector).toContainText('Không gửi: body_md')
  await expect(inspector).not.toContainText('Task chỉ hiện trong rail')
  expect(messagePosts).toBe(1)
  expect(observerGets).toBeGreaterThan(0)
})
