import assert from 'node:assert/strict'
import { beforeEach, test, vi } from 'vitest'

const { apiRequest, toastError } = vi.hoisted(() => ({
  apiRequest: vi.fn(),
  toastError: vi.fn(),
}))

vi.mock('../src/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../src/api')>()
  return { ...original, apiRequest }
})

vi.mock('sonner', () => ({
  toast: { error: toastError },
}))

const { restoreTask } = await import('../src/task-undo')

beforeEach(() => {
  apiRequest.mockReset()
  toastError.mockReset()
})

test('restore posts to the task restore endpoint and refreshes after success', async () => {
  apiRequest.mockResolvedValue({ id: 'task-1', status: 'restored' })
  const refresh = vi.fn()

  await restoreTask('task-1', refresh)

  assert.deepEqual(apiRequest.mock.calls, [
    ['/api/tasks/task-1/restore', { method: 'POST' }],
  ])
  assert.equal(refresh.mock.calls.length, 1)
  assert.equal(toastError.mock.calls.length, 0)
})

test('restore failure is reported through the shared toast error path', async () => {
  apiRequest.mockRejectedValue(new Error('network failed'))
  const refresh = vi.fn()

  await restoreTask('task-1', refresh)

  assert.deepEqual(toastError.mock.calls, [['Không kết nối được API.']])
  assert.equal(refresh.mock.calls.length, 0)
})
