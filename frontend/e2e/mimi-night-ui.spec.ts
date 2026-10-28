import { expect, type Page } from '@playwright/test'
import { test } from './fixtures/tasks'
import type { MimiChangeSet, MimiConversation } from '../src/mimi-api'

const conversationId = 'synthetic-night-conversation'
const finalId = 'synthetic-final-answer'
const timestamp = '2026-10-29T00:00:00Z'

function preview(id: string, title: string): MimiChangeSet {
  return { id, run_id: `run-${id}`, state: 'pending', digest: id.repeat(64).slice(0, 64),
    nonce: `nonce-${id}`, expires_at: '2099-01-01T00:00:00Z', policy_version: 'synthetic',
    operation: { operation_id: `op-${id}`, tool: 'task.create.v1', args: {
      id: `task-${id}`, title, body_md: null, status: 'open', priority: null,
      due_precision: 'none', due_on: null, due_at: null, is_private: false, items: [],
    } } }
}

async function setup(page: Page) {
  const conversation: MimiConversation = {
    id: conversationId, title: 'Hội thoại tổng hợp ca đêm', sensitivity: 'standard', generation: 1,
    messages: [{ id: finalId, role: 'assistant', sequence: 1, content: 'Câu trả lời cuối tổng hợp.',
      run_id: null, client_id: null, created_at: timestamp }],
    runs: [], change_sets: [], receipts: [], events: [], feedback: [],
  }
  const feedback: Array<Record<string, string>> = []
  const sends: Array<Record<string, string>> = []
  const decisions: Array<Record<string, string>> = []
  const state = { conversation, feedback, sends, decisions, failFeedback: false, failSnapshot: false, wrongDecisionAck: false, staleAfterDecision: false,
    feedbackGate: null as Promise<void> | null,
    streamResult: null as MimiConversation | null }
  await page.route('**/api/me', route => route.fulfill({ json: { email: 'synthetic@example.test',
    expires_at: '2099-01-01T00:00:00Z', private_until: null, private_locked_until: null,
    pin_is_set: true, pin_is_bootstrap: false, mimi_available: true } }))
  await page.route('**/api/mimi/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/messages/stream')) {
      sends.push(request.postDataJSON())
      if (state.streamResult) state.conversation = state.streamResult
      return route.fulfill({ contentType: 'text/event-stream',
        body: `event: conversation.snapshot\ndata: ${JSON.stringify(state.conversation)}\n\n` })
    }
    if (path.endsWith('/decision')) {
      const body = request.postDataJSON()
      decisions.push(body)
      const id = path.split('/').at(-2)!
      if (!state.staleAfterDecision) state.conversation = { ...state.conversation, change_sets: state.conversation.change_sets.map(item =>
        item.id === id ? { ...item, state: 'rejected' } : item) }
      return route.fulfill({ json: { change_set_id: state.wrongDecisionAck ? 'wrong-change' : id, state: 'rejected' } })
    }
    if (path.endsWith('/feedback') && request.method() === 'POST') {
      const body = request.postDataJSON()
      feedback.push(body)
      if (state.feedbackGate) await state.feedbackGate
      if (state.failFeedback) return route.fulfill({ status: 503, json: { detail: 'synthetic_feedback_unavailable' } })
      return route.fulfill({ json: { id: `feedback-${feedback.length}`, ...body, state: 'saved',
        unresolved: true, created_at: timestamp } })
    }
    if (path.endsWith('/conversations/current') || path.endsWith(`/conversations/${conversationId}`)) {
      return state.failSnapshot
        ? route.fulfill({ status: 503, json: { detail: 'synthetic_snapshot_unavailable' } })
        : route.fulfill({ json: state.conversation })
    }
    if (path.endsWith('/conversations')) return route.fulfill({ json: { items: [{
      id: conversationId, title: state.conversation.title, sensitivity: 'standard', generation: 1,
      metadata_version: 1, archived_at: null, updated_at: timestamp,
    }], next_cursor: null } })
    if (path.endsWith('/capabilities')) return route.fulfill({ json: {
      context_v1_enabled: false, live_provider_enabled: false, context_limit: 131072,
      output_reserve: 4096, model_selection_enabled: false,
    } })
    if (path.endsWith('/metadata-warmup')) return route.fulfill({ json: { status: 'not_applicable', paid_calls: 0 } })
    // No unhandled endpoint is allowed to reach an actual API/model.
    return route.fulfill({ status: 404, json: { detail: 'synthetic_endpoint_not_supplied' } })
  })
  return state
}

async function openDock(page: Page) {
  await page.getByTestId('app-menu-open').click()
  await page.getByTestId('mimi-dock-open').click()
  await expect(page.getByTestId('mimi-side-chat')).toBeVisible()
  await expect(page.getByTestId('mimi-input')).toBeVisible()
}

test('feedback nested in dock stays actionable and Escape returns to the same thumb', async ({ page }, info) => {
  const state = await setup(page)
  await page.goto('/')
  await openDock(page)
  const dock = page.getByTestId('mimi-side-chat')
  const geometry = await dock.boundingBox()
  expect(geometry!.y).toBeGreaterThanOrEqual(0)
  expect(geometry!.y + geometry!.height).toBeLessThanOrEqual(page.viewportSize()!.height + 1)
  const down = dock.getByRole('button', { name: 'Chưa tốt · câu trả lời 1', exact: true, includeHidden: true })
  await down.click()
  const dialog = page.getByTestId('mimi-feedback')
  await expect(dialog).toBeVisible()
  // The background thumb remains enabled while a real modal owns pointer
  // events. This reproduces the observed shape without claiming its history.
  expect(await down.evaluate(button => {
    const box = button.getBoundingClientRect()
    return { disabled: (button as HTMLButtonElement).disabled,
      intercepted: !button.contains(document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2)) }
  })).toEqual({ disabled: false, intercepted: true })
  await dialog.locator('#mimi-feedback').fill('Góp ý tổng hợp chưa gửi.')
  await expect(dialog.locator('#mimi-feedback')).toBeFocused()
  await expect(dialog.getByRole('button', { name: 'Lưu feedback', exact: true })).toBeEnabled()
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(dock).toBeVisible()
  await expect(down).toBeFocused()
  await down.click()
  await expect(dialog.locator('#mimi-feedback')).toHaveValue('Góp ý tổng hợp chưa gửi.')
  await dialog.getByRole('button', { name: 'Lưu feedback', exact: true }).click()
  await expect(dialog.getByText('Feedback đã được xác nhận và gắn với mục đã chọn.')).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Đóng', exact: true })).toBeInViewport()
  expect(state.feedback).toHaveLength(1)
  expect(state.feedback[0].target_id).toBe(finalId)
  await page.screenshot({ path: info.outputPath('feedback.png'), scale: 'css' })
  await dialog.getByRole('button', { name: 'Đóng', exact: true }).click()
  await expect(dialog).toBeHidden()
  await expect(dock).toBeVisible()
  await expect(down).toBeFocused()
})

test('collection revise dismisses its modal before focusing the bound composer', async ({ page }) => {
  const state = await setup(page)
  const change = preview('a', 'Phương án A')
  change.operation = { operation_id: 'op-a', tool: 'task.collection.v1', args: {
    schema_version: 'mimi.task-collection.v1', entries: [{ id: 'task-a', before: null,
      after: { fields: { title: 'Task tổng hợp A' }, children: [] }, reminder_effect: {},
      command: { action: 'create', expected_collection_version: null, fields: { title: 'Task tổng hợp A' }, children: [], reminder: {} },
    }], selection_id: null,
  } }
  state.conversation.change_sets = [change]
  await page.goto('/')
  await openDock(page)
  await page.getByRole('button', { name: 'Xem và duyệt', exact: true }).click()
  await page.getByRole('button', { name: 'Sửa phương án này', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Duyệt toàn bộ 1 Task', exact: true })).toBeHidden()
  await expect(page.getByTestId('mimi-input')).toBeFocused()
  await expect(page.getByTestId('mimi-revision-target')).toBeVisible()
})

test('quick access survives scroll, preserves a domain draft and restores opener focus', async ({ page }, info) => {
  await setup(page)
  await page.goto('/')
  const draft = page.getByTestId('quick-add-input')
  await draft.fill('Bản nháp Task không được mất')
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(100)
  const menu = page.getByTestId('app-menu-open')
  const header = page.getByTestId('app-header')
  expect((await header.boundingBox())!.y).toBeGreaterThanOrEqual(0)
  await expect(menu).toBeInViewport()
  const trigger = page.getByTestId('mimi-quick-access')
  const box = (await trigger.boundingBox())!
  expect(box.width).toBeGreaterThanOrEqual(44)
  expect(box.height).toBeGreaterThanOrEqual(44)
  expect((await trigger.innerText()).trim()).toBe('')
  if (info.project.name === 'mobile') {
    const nav = (await page.getByRole('tablist', { name: 'Chọn nội dung' }).boundingBox())!
    expect(box.y + box.height).toBeLessThanOrEqual(nav.y)
  }
  await page.screenshot({ path: info.outputPath('quick-access-scrolled.png'), scale: 'css' })
  await trigger.click()
  await expect(page.getByTestId('mimi-input')).toBeFocused()
  await expect(page.getByTestId('leave-draft-confirm')).toBeHidden()
  await expect(trigger).toBeHidden()
  await page.getByRole('button', { name: 'Đóng side-chat', exact: true }).click()
  await expect(trigger).toBeFocused()
  await expect(draft).toHaveValue('Bản nháp Task không được mất')
  await expect(page.getByRole('tablist', { name: 'Chọn nội dung' }).getByRole('tab')).toHaveCount(5)
})

test('Alt+A is guarded while editing or in a dialog and focuses existing workspace', async ({ page }) => {
  await setup(page)
  await page.goto('/')
  const draft = page.getByTestId('quick-add-input')
  await draft.focus()
  await page.keyboard.press('Alt+a')
  await expect(page.getByTestId('mimi-side-chat')).toBeHidden()
  await page.getByTestId('app-menu-open').click()
  await page.keyboard.press('Alt+a')
  await expect(page.getByTestId('app-menu')).toBeVisible()
  await expect(page.getByTestId('mimi-side-chat')).toBeHidden()
  await page.keyboard.press('Escape')
  await page.keyboard.press('Control+Alt+a')
  await expect(page.getByTestId('mimi-side-chat')).toBeHidden()
  await page.keyboard.press('Alt+a')
  await expect(page.getByTestId('mimi-input')).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('mimi-side-chat')).toBeHidden()
  await page.getByRole('tab', { name: 'Mimi', exact: true }).click()
  await expect(page.getByTestId('mimi-input')).toBeVisible()
  await page.getByTestId('app-menu-open').focus()
  await page.keyboard.press('Alt+a')
  await expect(page.getByTestId('mimi-input')).toBeFocused()
  await expect(page.getByTestId('mimi-side-chat')).toBeHidden()
})

test('valid bound B replaces A; rejected B cannot resurrect A across reload', async ({ page }, info) => {
  const state = await setup(page)
  const a = preview('a', 'Phương án A tổng hợp')
  const b = preview('b', 'Phương án B tổng hợp')
  state.conversation.change_sets = [a]
  state.streamResult = { ...state.conversation, change_sets: [b, { ...a, state: 'stale' }] }
  await page.goto('/')
  await openDock(page)
  await page.getByRole('button', { name: 'Sửa phương án này', exact: true }).click()
  await page.getByTestId('mimi-input').fill('Sửa thành phương án B')
  await page.getByTestId('mimi-input').press('Enter')
  await expect(page.getByTestId('mimi-change-set')).toContainText('Phương án B tổng hợp')
  expect(state.sends[0]).toMatchObject({ intent: 'revise_pending_preview',
    expected_change_set_id: a.id, expected_change_set_digest: a.digest })
  await page.screenshot({ path: info.outputPath('replacement-b.png'), scale: 'css' })
  await page.getByRole('button', { name: 'Từ chối', exact: true }).click()
  await expect(page.getByTestId('mimi-change-set')).toBeHidden()
  expect(state.decisions).toHaveLength(1)
  expect(state.decisions[0]).toMatchObject({ digest: b.digest, nonce: b.nonce, decision: 'reject' })
  await page.reload()
  await openDock(page)
  await expect(page.getByTestId('mimi-change-set')).toBeHidden()
  expect(state.sends).toHaveLength(1)
})

test('blocked-new notice is truthful and rejected A never materializes a phantom B', async ({ page }) => {
  const state = await setup(page)
  const a = preview('a', 'Phương án A vẫn giữ')
  state.conversation.change_sets = [a]
  state.conversation.runs = [{ id: 'blocked-run', generation: 1, state: 'halted', provider_outcome: 'succeeded',
    error_code: 'pending_preview_requires_decision', deadline: timestamp, created_at: timestamp, completed_at: timestamp }]
  await page.goto('/')
  await openDock(page)
  await expect(page.getByTestId('mimi-blocked-new-preview')).toContainText('chưa tạo preview mới')
  await expect(page.getByTestId('mimi-change-set')).toContainText('Phương án A vẫn giữ')
  // ACK succeeds but its following snapshot fails: retain usable chat/error,
  // remove the decided preview and never replay a mutation to repair a read.
  state.failSnapshot = true
  await page.getByRole('button', { name: 'Từ chối', exact: true }).click()
  await expect(page.getByTestId('mimi-change-set')).toBeHidden()
  await expect(page.getByTestId('mimi-blocked-new-preview')).toContainText('không tự tạo lại yêu cầu bị chặn')
  expect(state.decisions).toHaveLength(1)
  expect(state.sends).toHaveLength(0)
  state.failSnapshot = false
  await page.reload()
  await openDock(page)
  await expect(page.getByTestId('mimi-change-set')).toBeHidden()
})

test('failed feedback preserves exact target/key/payload and edited draft across retry', async ({ page }) => {
  const state = await setup(page)
  state.failFeedback = true
  await page.goto('/')
  await openDock(page)
  const down = page.getByRole('button', { name: 'Chưa tốt · câu trả lời 1', exact: true })
  await down.click()
  const dialog = page.getByTestId('mimi-feedback')
  await dialog.locator('#mimi-feedback').fill('Nội dung gửi ban đầu')
  await dialog.getByRole('button', { name: 'Lưu feedback', exact: true }).click()
  await expect(dialog.getByRole('button', { name: 'Thử lại feedback đã gửi', exact: true })).toBeEnabled()
  await expect(dialog).toContainText('Chưa xác nhận feedback đã lưu')
  await dialog.locator('#mimi-feedback').fill('Bản sửa đang giữ riêng')
  await page.keyboard.press('Escape')
  await down.click()
  state.failFeedback = false
  await dialog.getByRole('button', { name: 'Thử lại feedback đã gửi', exact: true }).click()
  await expect(dialog).toContainText('Feedback đã được xác nhận')
  expect(state.feedback).toHaveLength(2)
  expect(state.feedback[1]).toEqual(state.feedback[0])
  await expect(dialog.locator('#mimi-feedback')).toHaveValue('Bản sửa đang giữ riêng')
})

test('unresolved feedback and domain draft survive dock dismissal before an explicit retry', async ({ page }) => {
  const state = await setup(page)
  state.failFeedback = true
  await page.goto('/')
  await page.getByTestId('quick-add-input').fill('Bản nháp domain đang giữ')
  await openDock(page)
  const down = page.getByRole('button', { name: 'Chưa tốt · câu trả lời 1', exact: true })
  await down.click()
  const dialog = page.getByTestId('mimi-feedback')
  await dialog.locator('#mimi-feedback').fill('Góp ý chưa rõ kết quả')
  await dialog.getByRole('button', { name: 'Lưu feedback', exact: true }).click()
  await expect(dialog.getByRole('button', { name: 'Thử lại feedback đã gửi', exact: true })).toBeEnabled()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Đóng side-chat', exact: true }).click()
  await openDock(page)
  await down.click()
  await expect(dialog.locator('#mimi-feedback')).toHaveValue('Góp ý chưa rõ kết quả')
  state.failFeedback = false
  await dialog.getByRole('button', { name: 'Thử lại feedback đã gửi', exact: true }).click()
  await expect(dialog).toContainText('Feedback đã được xác nhận')
  expect(state.feedback).toHaveLength(2)
  expect(state.feedback[1]).toEqual(state.feedback[0])
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Đóng side-chat', exact: true }).click()
  await expect(page.getByTestId('quick-add-input')).toHaveValue('Bản nháp domain đang giữ')
})

test('invalid revision retains exact preview and editable revision draft', async ({ page }) => {
  const state = await setup(page)
  const a = preview('a', 'Phương án được giữ nguyên')
  state.conversation.change_sets = [a]
  state.streamResult = { ...state.conversation, runs: [{ id: 'invalid-revision', generation: 2, state: 'halted',
    provider_outcome: 'failed', deadline: timestamp, error_code: 'provider_contract_invalid', created_at: timestamp, completed_at: timestamp }] }
  await page.goto('/')
  await openDock(page)
  await page.getByRole('button', { name: 'Sửa phương án này', exact: true }).click()
  await page.getByTestId('mimi-input').fill('Nội dung sửa chưa thành preview hợp lệ')
  await page.getByTestId('mimi-input').press('Enter')
  await expect(page.getByTestId('mimi-change-set')).toContainText('Phương án được giữ nguyên')
  await expect(page.getByTestId('mimi-input')).toHaveValue('Nội dung sửa chưa thành preview hợp lệ')
  await expect(page.getByTestId('mimi-revision-target')).toBeVisible()
  expect(state.decisions).toHaveLength(0)
  expect(state.conversation.change_sets[0]).toEqual(a)
})

test('ambiguous active previews fail closed without choosing by array order', async ({ page }) => {
  const state = await setup(page)
  state.conversation.change_sets = [preview('a', 'A'), preview('b', 'B')]
  await page.goto('/')
  await openDock(page)
  await expect(page.getByTestId('mimi-preview-conflict')).toBeVisible()
  await expect(page.getByTestId('mimi-change-set')).toBeHidden()
  expect(state.decisions).toHaveLength(0)
})

for (const wrongAck of [false, true]) {
  test(`${wrongAck ? 'wrong ACK keeps UNKNOWN' : 'stale read after exact ACK stays blocked'} without decision replay`, async ({ page }) => {
    const state = await setup(page)
    state.conversation.change_sets = [preview('a', 'A')]
    state.staleAfterDecision = true
    state.wrongDecisionAck = wrongAck
    await page.goto('/')
    await openDock(page)
    await page.getByRole('button', { name: 'Từ chối', exact: true }).click()
    if (wrongAck) await expect(page.getByTestId('mimi-unknown-recovery')).toContainText('Chưa biết kết quả ghi')
    else await expect(page.getByTestId('mimi-preview-refresh')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Từ chối', exact: true })).toBeDisabled()
    await expect(page.getByRole('button', { name: 'Sửa phương án này', exact: true })).toBeDisabled()
    expect(state.decisions).toHaveLength(1)
    expect(state.sends).toHaveLength(0)
  })
}

test('workspace answer and verified notice both accept bound feedback without stale overlays', async ({ page }, info) => {
  const state = await setup(page)
  state.conversation.messages.push({ id: 'synthetic-notice', run_id: 'notice-run', client_id: null,
    sequence: 2, role: 'assistant', content: 'Thông báo tổng hợp từ server.', created_at: timestamp,
    provenance: { origin: 'server_notice', producer_code: 'pending_preview_requires_decision', version: 1,
      event_sequence: 1, source: 'server_verified' } })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Mimi', exact: true }).click()
  await page.getByRole('button', { name: 'Hữu ích · câu trả lời 1', exact: true }).click()
  const dialog = page.getByTestId('mimi-feedback')
  await expect(dialog).toContainText('Đã ghi nhận phản hồi tích cực')
  await dialog.getByRole('button', { name: 'Để sau', exact: true }).click()
  const notice = page.getByTestId('mimi-system-notice')
  await notice.getByRole('button', { name: /Chưa tốt/ }).click()
  await expect(dialog).toContainText('Đã ghi nhận phản hồi chưa tốt')
  expect(state.feedback.map(item => item.target_id)).toEqual([finalId, 'synthetic-notice'])
  await page.screenshot({ path: info.outputPath('workspace-notice-feedback.png'), scale: 'css' })
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(notice.getByRole('button', { name: /Chưa tốt/ })).toBeFocused()
})

test('late feedback ACK after dock remount preserves the newer draft without automatic replay', async ({ page }) => {
  const state = await setup(page)
  let release = () => {}
  state.feedbackGate = new Promise<void>(resolve => { release = resolve })
  await page.goto('/')
  await openDock(page)
  const down = page.getByRole('button', { name: 'Chưa tốt · câu trả lời 1', exact: true })
  await down.click()
  const dialog = page.getByTestId('mimi-feedback')
  await dialog.locator('#mimi-feedback').fill('Nội dung đang chờ ACK')
  await dialog.getByRole('button', { name: 'Lưu feedback', exact: true }).click()
  await expect.poll(() => state.feedback.length).toBe(1)
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Đóng side-chat', exact: true }).click()
  await openDock(page)
  await down.click()
  await dialog.locator('#mimi-feedback').fill('Bản nháp mới sau remount')
  release()
  await expect(dialog).toContainText('Feedback đã được xác nhận')
  await expect(dialog.locator('#mimi-feedback')).toHaveValue('Bản nháp mới sau remount')
  expect(state.feedback).toHaveLength(1)
})

test('small mobile/tablet/desktop shell keeps navigation clear and retains the same feedback draft', async ({ page }) => {
  await setup(page)
  await page.goto('/')
  for (const viewport of [{ width: 360, height: 740 }, { width: 1024, height: 768 }, { width: 1440, height: 900 }]) {
    await page.setViewportSize(viewport)
    await openDock(page)
    const dock = page.getByTestId('mimi-side-chat')
    const box = (await dock.boundingBox())!
    expect(box.y).toBeGreaterThanOrEqual(0)
    expect(box.y + box.height).toBeLessThanOrEqual(viewport.height + 1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const input = (await page.getByTestId('mimi-input').boundingBox())!
    expect(input.y + input.height).toBeLessThanOrEqual(viewport.height + 1)
    await page.getByRole('button', { name: 'Chưa tốt · câu trả lời 1', exact: true }).click()
    const dialog = page.getByTestId('mimi-feedback')
    if (viewport.width !== 360) await expect(dialog.locator('#mimi-feedback')).toHaveValue('Giữ qua các kích thước')
    await dialog.locator('#mimi-feedback').fill('Giữ qua các kích thước')
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: 'Đóng side-chat', exact: true }).click()
    await expect(page.getByTestId('mimi-quick-access')).toBeInViewport()
  }
})
