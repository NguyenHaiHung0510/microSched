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

const { restoreTask } = await import('../src/task-undo')
const client = {} as QueryClient

beforeEach(() => {
  queuedRequest.mockReset().mockResolvedValue(null)
  restoreCancelledOutbox.mockReset()
  applyOverlay.mockReset().mockResolvedValue(undefined)
  toastError.mockReset()
  vi.stubGlobal('window', { dispatchEvent })
  dispatchEvent.mockReset()
})

test('server-backed restore is a queued POST with the full typed projection and no guessed body DTO', async () => {
  const task = { id: '550e8400-e29b-41d4-a716-446655440000', title: 'Keep all fields', is_private: true, items: [{ id: 'child' }] }
  await restoreTask(client, task, null)
  assert.equal(queuedRequest.mock.calls.length, 1)
  assert.equal(queuedRequest.mock.calls[0][1], 'task.restore')
  assert.deepEqual(queuedRequest.mock.calls[0][2], {
    path: `/api/tasks/${task.id}/restore`, entityId: task.id, requiresPrivate: true,
    optimisticEntity: task,
  })
  assert.equal(toastError.mock.calls.length, 0)
})

test('an unsent create cancellation restores the original command tree without a restore POST', async () => {
  const receipt = { cancelledRows: [{ operation_id: 1, operation_kind: 'task.create' }, { operation_id: 2, operation_kind: 'task_item.create' }] }
  const restoredRows = [{ operation_id: 11, operation_kind: 'task.create' }, { operation_id: 12, operation_kind: 'task_item.create' }]
  restoreCancelledOutbox.mockResolvedValue(restoredRows)
  await restoreTask(client, { id: 'task', is_private: false }, receipt as never)
  assert.equal(restoreCancelledOutbox.mock.calls[0][0], receipt.cancelledRows)
  assert.deepEqual(applyOverlay.mock.calls, [[client, restoredRows[0]], [client, restoredRows[1]]])
  assert.equal(queuedRequest.mock.calls.length, 0)
  assert.equal(dispatchEvent.mock.calls.length, 1)
})

test('invalid cancellation receipt is reported without issuing an unrelated server restore', async () => {
  restoreCancelledOutbox.mockRejectedValue(new Error('invalid receipt'))
  await restoreTask(client, { id: 'task', is_private: false }, { cancelledRows: [{}] } as never)
  assert.equal(queuedRequest.mock.calls.length, 0)
  assert.deepEqual(toastError.mock.calls, [['Không kết nối được API.']])
})
