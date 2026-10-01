import assert from 'node:assert/strict'
import { beforeEach, test, vi } from 'vitest'
import type { QueryClient } from '@tanstack/react-query'

const { queuedRequest, restoreCancelledOutbox, applyOverlay, toastError, dispatchEvent } = vi.hoisted(() => ({
  queuedRequest: vi.fn(),
  restoreCancelledOutbox: vi.fn(),
  applyOverlay: vi.fn(),
  toastError: vi.fn(),
  dispatchEvent: vi.fn(),
}))

vi.mock('../src/lib/queued-mutation', () => ({ queuedRequest }))
vi.mock('../src/lib/outbox-db', () => ({ restoreCancelledOutbox }))
vi.mock('../src/lib/outbox-adapters', () => ({ adapterFor: () => ({ optimisticApply: applyOverlay }) }))
vi.mock('sonner', () => ({ toast: { error: toastError } }))

const { restoreNote } = await import('../src/note-undo')
const client = {} as QueryClient

beforeEach(() => {
  queuedRequest.mockReset().mockResolvedValue(null)
  restoreCancelledOutbox.mockReset()
  applyOverlay.mockReset().mockResolvedValue(undefined)
  toastError.mockReset()
  vi.stubGlobal('window', { dispatchEvent })
  dispatchEvent.mockReset()
})

test('server-backed note restore queues the known full note and privacy classification', async () => {
  const note = {
    id: '550e8400-e29b-41d4-a716-446655440040', title: 'Private note', body_md: 'body',
    is_private: true, pinned: false, items: [{ id: 'item', content: 'child' }],
  }
  await restoreNote(client, note, null)
  assert.equal(queuedRequest.mock.calls.length, 1)
  assert.equal(queuedRequest.mock.calls[0][1], 'note.restore')
  assert.deepEqual(queuedRequest.mock.calls[0][2], {
    path: `/api/notes/${note.id}/restore`, entityId: note.id, requiresPrivate: true,
    optimisticEntity: note,
  })
})

test('cancelled unsent note tree is restored with remapped commands, without a POST', async () => {
  const cancelledRows = [{ operation_id: 1, operation_kind: 'note.create' }, { operation_id: 2, operation_kind: 'note_item.create' }]
  const restoredRows = [{ operation_id: 21, operation_kind: 'note.create' }, { operation_id: 22, operation_kind: 'note_item.create' }]
  restoreCancelledOutbox.mockResolvedValue(restoredRows)
  await restoreNote(client, { id: 'note', is_private: false }, { cancelledRows } as never)
  assert.equal(restoreCancelledOutbox.mock.calls[0][0], cancelledRows)
  assert.deepEqual(applyOverlay.mock.calls, [[client, restoredRows[0]], [client, restoredRows[1]]])
  assert.equal(queuedRequest.mock.calls.length, 0)
  assert.equal(dispatchEvent.mock.calls.length, 1)
})
