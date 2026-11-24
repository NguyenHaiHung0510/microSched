import { afterEach, expect, test, vi } from 'vitest'
import { fetchMimiReceiptDiff, prepareMimiUndo, type MimiReceiptDiff } from './mimi-api'

const diff: MimiReceiptDiff = {
  receipt_id: 'receipt-a', executed_at: '2026-11-16T01:00:00Z', undo_available: true,
  plan: { schema_version: 'mimi.task-collection.v1', selection_id: null, entries: [{
    id: 'task-a', command: { action: 'edit', expected_collection_version: 2, fields: {}, children: [], reminder: { action: 'keep' } },
    before: { fields: { title: 'Trước A' }, children: [] },
    after: { fields: { title: 'Sau A' }, children: [] }, reminder_effect: { action: 'keep' },
  }] },
}
const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
afterEach(() => vi.unstubAllGlobals())

test('diff is an explicit receipt GET, abortable and outside HTTP cache; undo keeps the existing POST path', async () => {
  const request = vi.fn().mockResolvedValueOnce(reply(diff)).mockResolvedValueOnce(reply({ id: 'conversation-a' }))
  vi.stubGlobal('fetch', request)
  const controller = new AbortController()
  expect(await fetchMimiReceiptDiff('receipt-a', controller.signal)).toEqual(diff)
  expect(request.mock.calls[0][0]).toBe('/api/mimi/receipts/receipt-a/diff')
  expect(request.mock.calls[0][1]).toMatchObject({ cache: 'no-store', credentials: 'same-origin' })
  expect(request.mock.calls[0][1].method).toBeUndefined()
  controller.abort()
  expect(request.mock.calls[0][1].signal.aborted).toBe(true)
  await prepareMimiUndo('receipt-a')
  expect(request.mock.calls[1][0]).toBe('/api/mimi/receipts/receipt-a/undo-preview')
  expect(request.mock.calls[1][1]).toMatchObject({ method: 'POST', headers: { 'X-Mimi-CSRF': '1' }, body: '{}' })
})

test('receipt identity is encoded as one path segment without rewriting the durable ID', async () => {
  const request = vi.fn().mockResolvedValue(reply({ ...diff, receipt_id: 'a/b?x' }))
  vi.stubGlobal('fetch', request)
  await fetchMimiReceiptDiff('a/b?x')
  expect(request.mock.calls[0][0]).toBe('/api/mimi/receipts/a%2Fb%3Fx/diff')
})

test.each([
  null,
  { ...diff, receipt_id: 'receipt-b' },
  { ...diff, plan: null },
  { ...diff, plan: { ...diff.plan, entries: [] } },
  { ...diff, plan: { ...diff.plan, entries: [{ ...diff.plan.entries[0], after: null }] } },
  { ...diff, executed_at: 'invalid' },
  { ...diff, undo_available: null },
])('null or invalid committed projections never become a usable diff: %j', async payload => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(payload)))
  if (payload === null) expect(await fetchMimiReceiptDiff('receipt-a')).toBeNull()
  else await expect(fetchMimiReceiptDiff('receipt-a')).rejects.toThrow('Mimi receipt diff response mismatch')
})

test.each([403, 404, 409, 410, 503])('HTTP %s stays a read failure and does not fall back to a different receipt', async status => {
  const request = vi.fn().mockResolvedValue(reply({ detail: 'synthetic-diff-unavailable' }, status))
  vi.stubGlobal('fetch', request)
  await expect(fetchMimiReceiptDiff('receipt-a')).rejects.toMatchObject({ status })
  expect(request).toHaveBeenCalledTimes(1)
})
