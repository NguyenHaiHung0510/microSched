import { afterEach, expect, test, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { ButtonHTMLAttributes } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ApiError } from './api'
import { MimiAppliedReceipt } from './MimiAppliedReceipt'
import { MimiCollectionEntryDetails } from './MimiCollectionEntryDetails'
import { MimiScreen } from './MimiScreen'
import { appliedMimiReceiptId } from './mimi-message-provenance'
import type { MimiCollectionPlan, MimiConversation, MimiMessage, MimiReceiptDiff, MimiResponseTiming, MimiRun } from './mimi-api'

const buttons = vi.hoisted(() => [] as Array<ButtonHTMLAttributes<HTMLButtonElement>>)
vi.mock('@/components/ui/button', async importOriginal => {
  const actual = await importOriginal<typeof import('@/components/ui/button')>()
  return { ...actual, Button: (props: ButtonHTMLAttributes<HTMLButtonElement>) => {
    buttons.push(props)
    return <actual.Button {...props} />
  } }
})

const clients: QueryClient[] = []
function client() {
  const value = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.push(value)
  return value
}
const timestamp = '2026-11-16T01:00:00Z'
const plan = (label = 'A'): MimiCollectionPlan => ({
  schema_version: 'mimi.task-collection.v1', selection_id: 'selection-unrelated-to-diff',
  entries: [{
    id: `task-${label}`, command: { action: 'edit', expected_collection_version: 2, fields: {}, children: [], reminder: { action: 'keep' } },
    before: { fields: { title: `Trước ${label}`, body_md: 'Nội dung cũ đầy đủ' }, children: [{ id: 'child', content: 'Checklist cũ', is_completed: false, position: 0 }], reminder: null },
    after: { fields: { title: `Sau ${label}`, body_md: 'Nội dung mới đầy đủ' }, children: [{ id: 'child', content: 'Checklist mới', is_completed: true, position: 0 }], reminder: { status: 'pending', mode: 'absolute', due_at: timestamp } },
    reminder_effect: { action: 'configure' },
  }],
})
const diff = (id = 'receipt-a', label = 'A'): MimiReceiptDiff => ({ receipt_id: id, plan: plan(label), undo_available: true, executed_at: timestamp })
const notice = (receiptId: string | null = 'receipt-a', id = 'notice-a'): MimiMessage => ({
  id, applied_receipt_id: receiptId, run_id: 'run-a', client_id: null, sequence: 2, role: 'assistant',
  content: 'Đã áp dụng thay đổi.', created_at: timestamp,
  provenance: { source: 'server_verified', origin: 'server_notice', version: 1, event_sequence: 3, producer_code: 'collection_committed' },
})
const diffKey = (receiptId = 'receipt-a', messageId = 'notice-a') => ['mimi', 'receipt-diff', 'conversation-a', messageId, receiptId]
const props = { conversationId: 'conversation-a', messageId: 'notice-a', receiptId: 'receipt-a', undoPending: false, undoDisabled: false, undoError: null, onUndo: vi.fn(), onOpenTasks: vi.fn() }
function renderReceipt(q: QueryClient, extra: Partial<typeof props> = {}) {
  buttons.length = 0
  return renderToStaticMarkup(<QueryClientProvider client={q}><MimiAppliedReceipt {...props} {...extra} /></QueryClientProvider>)
}
const button = (text: string) => buttons.find(value => value.children === text)!
afterEach(() => {
  clients.splice(0).forEach(q => q.clear())
  props.onUndo.mockClear(); props.onOpenTasks.mockClear()
  vi.unstubAllGlobals()
})

test('only verified applied notice metadata binds a receipt; identical text, run or timing is insufficient', () => {
  expect(appliedMimiReceiptId(notice())).toBe('receipt-a')
  expect(appliedMimiReceiptId({ ...notice(), provenance: { ...notice().provenance!, producer_code: 'operation_committed' } })).toBe('receipt-a')
  for (const message of [
    notice(null), { ...notice(), applied_receipt_id: undefined }, { ...notice(), applied_receipt_id: ' ' },
    { ...notice(), provenance: undefined }, { ...notice(), role: 'user' as const }, { ...notice(), run_id: null },
    { ...notice(), provenance: { ...notice().provenance!, producer_code: 'preview_prepared' } },
    { ...notice(), provenance: { ...notice().provenance!, source: 'absent_or_unverified' as const } },
  ]) expect(appliedMimiReceiptId(message)).toBeNull()
})

test('read-only frame reuses the committed table and undo targets only the supplied durable receipt', () => {
  const q = client()
  q.setQueryData(diffKey(), diff())
  const html = renderReceipt(q)
  expect(html).toContain('data-testid="mimi-applied-receipt"')
  expect(html).toContain('Trước A'); expect(html).toContain('Sau A')
  expect(html).toContain('Chỉ đọc'); expect(html).toContain('Tìm trong thay đổi đã áp dụng')
  for (const text of ['Chờ bạn duyệt', 'mimi-preview-actions', 'Xác nhận toàn bộ', 'Sửa phương án này', 'Từ chối', 'Task sẽ thay đổi', 'Hết hạn']) expect(html).not.toContain(text)
  button('Chuẩn bị hoàn tác').onClick?.({} as never)
  expect(props.onUndo).toHaveBeenCalledExactlyOnceWith('receipt-a')
  button('Mở Task').onClick?.({} as never)
  expect(props.onOpenTasks).toHaveBeenCalledOnce()
  expect(q.getQueryCache().getAll().some(query => query.queryKey[1] === 'selection')).toBe(false)
})

test.each([{ undoPending: true }, { undoDisabled: true }])('undo respects existing pending/run/decision fences: %j', extra => {
  const q = client(); q.setQueryData(diffKey(), diff())
  renderReceipt(q, extra)
  expect(button('Chuẩn bị hoàn tác').disabled).toBe(true)
})

test('undo availability is taken from the diff and never inferred from another receipt', () => {
  const q = client(); q.setQueryData(diffKey(), { ...diff(), undo_available: false })
  expect(renderReceipt(q)).toContain('hiện không có hoàn tác')
  expect(button('Chuẩn bị hoàn tác')).toBeUndefined()
})

test('missing, null and wrong-identity diff render no before/after or undo', () => {
  const q = client()
  expect(renderReceipt(q)).toContain('Đang đọc thay đổi đã lưu')
  expect(button('Chuẩn bị hoàn tác')).toBeUndefined()
  for (const payload of [null, diff('receipt-b', 'B')]) {
    q.setQueryData(diffKey(), payload)
    const html = renderReceipt(q)
    expect(html).toContain('không có chi tiết trước/sau')
    expect(html).not.toContain('data-testid="mimi-review-row"')
    expect(button('Chuẩn bị hoàn tác')).toBeUndefined()
  }
})

test.each([403, 404, 409, 410, 503])('failed re-read %s hides a previously cached projection and offers explicit retry', async status => {
  const q = client(); q.setQueryData(diffKey(), diff())
  const fetcher = vi.fn().mockRejectedValue(new ApiError(status, 'synthetic-failure'))
  await expect(q.fetchQuery({ queryKey: diffKey(), queryFn: fetcher, retry: false })).rejects.toThrow()
  const html = renderReceipt(q)
  expect(html).toContain('Thông báo đã áp dụng vẫn được giữ')
  expect(html).not.toContain('Sau A')
  expect(html).not.toContain('data-testid="mimi-review-row"')
  expect(button('Chuẩn bị hoàn tác')).toBeUndefined()
  expect(button('Đọc lại chi tiết')).toBeDefined()
})

test('in-flight re-read hides cached details until the exact receipt is verified again', async () => {
  const q = client(); q.setQueryData(diffKey(), diff())
  let finish!: (value: MimiReceiptDiff) => void
  const request = q.fetchQuery({ queryKey: diffKey(), queryFn: () => new Promise<MimiReceiptDiff>(resolve => { finish = resolve }) })
  expect(renderReceipt(q)).toContain('Đang đọc thay đổi đã lưu')
  expect(button('Chuẩn bị hoàn tác')).toBeUndefined()
  finish(diff()); await request
  expect(renderReceipt(q)).toContain('Sau A')
})

test('explicit retry reads the same receipt and never posts an action', async () => {
  const q = client(); q.setQueryData(diffKey(), null)
  const request = vi.fn().mockResolvedValue(new Response(JSON.stringify(diff()), { status: 200, headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', request)
  renderReceipt(q)
  button('Đọc lại chi tiết').onClick?.({} as never)
  await vi.waitFor(() => expect(q.getQueryData(diffKey())).toEqual(diff()))
  expect(request).toHaveBeenCalledTimes(1)
  expect(request.mock.calls[0][0]).toBe('/api/mimi/receipts/receipt-a/diff')
  expect(request.mock.calls[0][1].method).toBeUndefined()
})

test('executed full detail renderer keeps exact fields/checklist/reminder and uses committed copy', () => {
  const entry = plan().entries[0]
  const frozen = JSON.stringify(entry)
  const html = renderToStaticMarkup(<MimiCollectionEntryDetails entry={entry} executed />)
  for (const text of ['Nội dung cũ đầy đủ', 'Nội dung mới đầy đủ', 'Checklist cũ', 'Checklist mới', 'Lời nhắc sau khi áp dụng', 'Thời điểm cụ thể', 'phiên bản trước khi áp dụng']) expect(html).toContain(text)
  expect(html).not.toContain('phiên bản chờ xác nhận')
  expect(html).not.toContain('Hiệu ứng sau khi xác nhận')
  expect(JSON.stringify(entry)).toBe(frozen)
})

function renderScreen(q: QueryClient, conversation: MimiConversation, variant: 'workspace' | 'dock' = 'workspace') {
  q.setQueryData(['mimi', 'conversation', conversation.id], conversation)
  return renderToStaticMarkup(<QueryClientProvider client={q}><MimiScreen variant={variant} conversationId={conversation.id} onOpenTasks={() => {}} /></QueryClientProvider>)
}
function screenFixture(): MimiConversation {
  return { id: 'conversation-a', sensitivity: 'standard', generation: 1,
    messages: [notice()], runs: [], change_sets: [], events: [], feedback: [],
    receipts: ['receipt-a', 'receipt-b'].map(id => ({ id, change_set_id: `change-${id}`, operation_id: `op-${id}`, task_id: 'task-a', digest: 'a'.repeat(64), executed_at: timestamp, result: { count: 1, undo_available: true } })),
  }
}

test('reload keeps each notice bound despite a later receipt; duplicate tail suppression is exact', () => {
  vi.stubGlobal('navigator', { onLine: true }); vi.stubGlobal('document', { hidden: false })
  const q = client(); q.setQueryData(diffKey(), diff())
  const snapshot = screenFixture()
  let html = renderScreen(q, JSON.parse(JSON.stringify(snapshot)))
  expect(html).toContain('data-mimi-response-id="notice-a"')
  expect(html).toContain('Sau A')
  expect(html).toContain('data-testid="mimi-receipt"')
  expect(html).toContain('Receipt receipt-b')
  snapshot.messages.push(notice('receipt-b', 'notice-b'))
  q.setQueryData(diffKey('receipt-b', 'notice-b'), diff('receipt-b', 'B'))
  html = renderScreen(q, JSON.parse(JSON.stringify(snapshot)))
  expect(html.match(/data-testid="mimi-applied-receipt"/g)).toHaveLength(2)
  expect(html.indexOf('notice-a')).toBeLessThan(html.indexOf('Sau A'))
  expect(html.indexOf('Sau A')).toBeLessThan(html.indexOf('notice-b'))
  expect(html.indexOf('notice-b')).toBeLessThan(html.indexOf('Sau B'))
  expect(html).not.toContain('data-testid="mimi-receipt"')
  snapshot.messages = [notice(null)]
  html = renderScreen(q, snapshot)
  expect(html).not.toContain('data-testid="mimi-applied-receipt"')
  expect(html).toContain('data-testid="mimi-receipt"')
})

test('message, verified notice and applied receipt render the same Vietnam midnight', () => {
  vi.stubGlobal('navigator', { onLine: true }); vi.stubGlobal('document', { hidden: false })
  const instant = '2026-11-18T17:35:06Z'
  const q = client(), snapshot = screenFixture()
  snapshot.messages = [
    { id: 'user-message', run_id: null, client_id: null, sequence: 1, role: 'user', content: 'Lịch ngày mai', created_at: instant },
    { ...notice(), created_at: instant },
  ]
  q.setQueryData(diffKey(), { ...diff(), executed_at: instant })
  const html = renderScreen(q, snapshot)
  expect(html).toContain('<time class="mimi-message-time">00:35</time>')
  const vnLabel = new Date(instant).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })
  expect(html.split(`<time dateTime="${instant}">${vnLabel}</time>`)).toHaveLength(3)
})

test.each(['workspace', 'dock'] as const)('%s shows a failed confirmation and its real error without terminal diagnostics', variant => {
  vi.stubGlobal('navigator', { onLine: true }); vi.stubGlobal('document', { hidden: false })
  const q = client(), snapshot = screenFixture()
  q.setQueryData(diffKey(), diff())
  snapshot.runs.push({ id: 'failed-run', mode: 'text', generation: 1, state: 'halted', provider_outcome: 'succeeded',
    deadline: timestamp, error_code: 'change_set_source_stale', created_at: timestamp, completed_at: timestamp })
  const failed = { run_id: 'failed-run', outcome: 'failed' as const, parent_run_id: null, elapsed_ms: null, observation: 'missing', provenance: 'client' }
  snapshot.response_timings = { version: 1, scope: 'all_retained_response_segments', provenance: 'client',
    min_ms: null, avg_ms: null, max_ms: null, observed: 0, eligible: 0, missing: 0,
    pending: 0, failed: 2, cancelled: 0, unknown: 0, responses: [
      { ...failed, phase: 'send', source_id: 'submit', target_id: 'failed-run', response_kind: 'status' },
      { ...failed, phase: 'confirmation', source_id: 'failed-preview', target_id: 'failed-preview', response_kind: 'decision' },
    ] }
  const html = renderScreen(q, snapshot, variant)
  expect(Array.from(html.matchAll(/data-mimi-response-id="([^"]+)"/g), match => match[1])).toEqual(['notice-a', 'failed-preview'])
  expect(html).toContain('Kết quả quyết định preview · Chưa áp dụng')
  expect(html).toContain('Dữ liệu nguồn đã thay đổi; Mimi chưa tạo Task.')
  expect(html).toContain('data-testid="mimi-applied-receipt"')
  expect(html).toContain('Chuẩn bị hoàn tác')
  expect(html).not.toContain('data-testid="mimi-run-outcome"')
  for (const diagnostic of ['Trạng thái lượt chạy', 'mimi-answer-timing', 'E2E', 'phép đo browser', 'USD']) expect(html).not.toContain(diagnostic)
})

function terminalSnapshot(state: string, providerOutcome: MimiRun['provider_outcome'], error: string | null, outcome: MimiResponseTiming['outcome']): MimiConversation {
  vi.stubGlobal('navigator', { onLine: true }); vi.stubGlobal('document', { hidden: false })
  const run = { id: 'last-run', mode: 'text' as const, generation: 1, state, provider_outcome: providerOutcome, error_code: error,
    resumable: false, deadline: timestamp, created_at: timestamp, completed_at: timestamp }
  return { ...screenFixture(), receipts: [], runs: [run],
    messages: [{ id: 'submitted-message', run_id: run.id, client_id: 'submit', sequence: 1, role: 'user', content: 'Lịch ngày mai', created_at: timestamp }],
    response_timings: { version: 1, scope: 'all_retained_response_segments', provenance: 'client',
      min_ms: null, avg_ms: null, max_ms: null, observed: 0, eligible: 0, missing: 0, pending: 0,
      failed: Number(outcome === 'failed'), cancelled: Number(outcome === 'cancelled'), unknown: Number(outcome === 'unknown'),
      responses: [{ run_id: run.id, target_id: run.id, source_id: 'submit', phase: 'send', response_kind: 'status',
        outcome, parent_run_id: null, elapsed_ms: null, observation: 'missing', provenance: 'client' }],
    },
  }
}

test.each([
  ['workspace', 'halted', 'failed', 'worker_failed', 'failed', 'Mimi đã dừng lượt này trước khi trả lời.'],
  ['dock', 'halted', 'succeeded', 'worker_failed', 'failed', 'Mimi đã dừng lượt này trước khi trả lời.'],
  ['workspace', 'cancelled', null, 'owner_cancelled', 'cancelled', 'Đã huỷ lượt này.'],
  ['dock', 'cancelled', 'failed', 'owner_cancelled', 'cancelled', 'Đã huỷ lượt này.'],
  ['dock', 'budget_exceeded', null, 'compaction_preflight_or_reservation_failed', 'failed', 'Mimi đã dừng vì chưa thể chuẩn bị ngữ cảnh cho lượt này.'],
] as const)('%s reopens a no-answer %s run with one meaningful result', (variant, state, providerOutcome, error, outcome, label) => {
  const snapshot = terminalSnapshot(state, providerOutcome, error, outcome)
  snapshot.messages.unshift({ ...notice(null), id: 'prior-notice', run_id: 'prior-run', sequence: 0 })
  const html = renderScreen(client(), snapshot, variant)
  expect(html.match(/data-testid="mimi-run-outcome"/g) ?? []).toHaveLength(1)
  expect(html).toContain(label)
  expect(html).toContain('data-mimi-response-id="last-run"')
  expect(html).not.toMatch(/Trạng thái lượt chạy|E2E|USD|phép đo browser|Reconcile provider|>Tiếp tục</)
})

test.each(['outcome_unknown', 'cancelled'])('a %s run with unknown provider outcome keeps only Reconcile', state => {
  const cancelled = state === 'cancelled'
  const snapshot = terminalSnapshot(state, 'unknown', cancelled ? 'owner_cancelled' : 'worker_failed', cancelled ? 'cancelled' : 'unknown')
  const html = renderScreen(client(), snapshot)
  expect(html.match(/Reconcile provider/g)).toHaveLength(1)
  expect(html).toContain('Kết quả provider chưa xác định nên Mimi không tự gửi lại.')
  expect(html).not.toMatch(/mimi-run-outcome|data-mimi-response-id="last-run"|>Tiếp tục<|E2E|USD/)
})

test('a specific provider failure banner stays visible without an extra fallback', () => {
  const html = renderScreen(client(), terminalSnapshot('halted', 'failed', 'provider_reconciliation_failed', 'failed'))
  expect(html).toContain('Provider đã dừng và chưa trả kết quả dùng được.')
  expect(html).not.toMatch(/mimi-run-outcome|data-mimi-response-id="last-run"|E2E|USD/)
})

test('a known context limit keeps its original notice without an extra fallback', () => {
  const html = renderScreen(client(), terminalSnapshot('budget_exceeded', null, 'mimi_history_message_exceeds_context_window', 'failed'))
  expect(html).toContain('data-testid="mimi-context-limit-notice"')
  expect(html).toContain('Lượt này chưa vừa giới hạn context đã chọn.')
  expect(html).not.toMatch(/mimi-run-outcome|data-mimi-response-id="last-run"|E2E|USD/)
})

test('rejecting the preview shows its own decision instead of a generic cancellation', () => {
  const snapshot = terminalSnapshot('cancelled', 'succeeded', null, 'cancelled')
  const timing = snapshot.response_timings!
  timing.responses.push({ ...timing.responses[0], phase: 'confirmation', target_id: 'rejected-preview', source_id: 'rejected-preview', response_kind: 'decision' })
  const html = renderScreen(client(), snapshot)
  expect(html).toContain('Kết quả quyết định preview · Đã từ chối')
  expect(html).toContain('data-mimi-response-id="rejected-preview"')
  expect(html).not.toMatch(/mimi-run-outcome|data-mimi-response-id="last-run"|E2E|USD/)
})

test.each(['answer', 'verified notice'] as const)('a %s for the same halted run takes the place of fallback status', kind => {
  const snapshot = terminalSnapshot('halted', 'failed', 'worker_failed', 'failed')
  delete snapshot.response_timings
  const content = kind === 'answer' ? 'Đây là lịch đã đọc.' : 'Mimi không đọc được nguồn.'
  snapshot.messages.push({ ...notice(null), id: 'real-response', run_id: 'last-run', content,
    provenance: kind === 'answer' ? undefined : { ...notice().provenance!, producer_code: 'provider_terminal' } })
  const html = renderScreen(client(), snapshot)
  expect(html).toContain(content)
  expect(html).toContain('data-mimi-response-id="real-response"')
  expect(html).not.toMatch(/mimi-run-outcome|data-mimi-response-id="last-run"|E2E|USD/)
})

test('a completed run with an unknown diagnostic segment does not claim an outcome in the transcript', () => {
  const html = renderScreen(client(), terminalSnapshot('completed', 'succeeded', null, 'unknown'))
  expect(html).toContain('Lịch ngày mai')
  expect(html).not.toMatch(/mimi-run-outcome|data-mimi-response-id="last-run"|Run đã dừng|Reconcile provider|E2E|USD/)
})

test('Voice 6+ pending preview remains available beside applied history after the Voice run ends', () => {
  vi.stubGlobal('navigator', { onLine: true }); vi.stubGlobal('document', { hidden: false })
  const q = client(), snapshot = screenFixture()
  const pendingPlan = plan('pending')
  pendingPlan.selection_id = null
  pendingPlan.entries = Array.from({ length: 6 }, (_, index) => ({ ...pendingPlan.entries[0], id: `pending-${index}` }))
  snapshot.change_sets.push({ id: 'voice-preview', run_id: 'voice-run', digest: 'b'.repeat(64), nonce: 'nonce', state: 'pending', policy_version: 'synthetic-policy-v1',
    expires_at: '2099-11-16T01:00:00Z', confirmation_preflight: { status: 'eligible', reason: null },
    operation: { operation_id: 'voice-operation', tool: 'task.collection.v1', args: pendingPlan } })
  snapshot.runs.push({ id: 'voice-run', mode: 'voice', generation: 1, state: 'completed', provider_outcome: 'succeeded',
    deadline: timestamp, error_code: null, created_at: timestamp, completed_at: timestamp })
  const html = renderScreen(q, snapshot)
  expect(html).toContain('Chờ bạn duyệt · 6 Task')
  expect(html).toContain('Xem và duyệt')
  expect(html).toContain('data-testid="mimi-change-set"')
  expect(html).toContain('data-testid="mimi-applied-receipt"')
  expect(html).not.toContain('data-testid="mimi-pending-answer"')
})
