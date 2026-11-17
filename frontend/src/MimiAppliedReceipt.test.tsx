import { afterEach, expect, test, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { ButtonHTMLAttributes } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ApiError } from './api'
import { MimiAppliedReceipt } from './MimiAppliedReceipt'
import { MimiCollectionEntryDetails } from './MimiCollectionEntryDetails'
import { MimiScreen } from './MimiScreen'
import { appliedMimiReceiptId } from './mimi-message-provenance'
import type { MimiCollectionPlan, MimiConversation, MimiMessage, MimiReceiptDiff } from './mimi-api'

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

function renderScreen(q: QueryClient, conversation: MimiConversation) {
  q.setQueryData(['mimi', 'conversation', conversation.id], conversation)
  return renderToStaticMarkup(<QueryClientProvider client={q}><MimiScreen conversationId={conversation.id} onOpenTasks={() => {}} /></QueryClientProvider>)
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
