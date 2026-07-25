import assert from 'node:assert/strict'
import { test } from 'vitest'

import { apiRequest, UnauthenticatedError } from '../src/api.ts'

test('apiRequest sends same-origin JSON and returns the decoded body', async () => {
  let captured: { path: RequestInfo | URL; init?: RequestInit } | undefined
  globalThis.fetch = async (path, init) => {
    captured = { path, init }
    return new Response(JSON.stringify({ id: 'task-1' }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  const body = await apiRequest('/api/tasks', {
    method: 'POST',
    body: JSON.stringify({ title: 'Việc mới' }),
  })

  assert.deepEqual(body, { id: 'task-1' })
  // Bộ chạy cũ không type-check file này (nó đi qua `--experimental-strip-types`),
  // nên `captured` chưa từng bị hỏi là đã được gán hay chưa. Giữ lại phép hỏi đó:
  // fetch không được gọi thì ba khẳng định dưới phải đỏ vì ĐÚNG lý do.
  assert.ok(captured, 'fetch không được gọi')
  assert.equal(captured.path, '/api/tasks')
  assert.equal(captured.init?.credentials, 'same-origin')
  assert.equal(
    (captured.init?.headers as Record<string, string>)['Content-Type'],
    'application/json',
  )
})

test('apiRequest turns 401 into the shared logged-out signal', async () => {
  globalThis.fetch = async () => new Response(null, { status: 401 })

  await assert.rejects(apiRequest('/api/tasks'), UnauthenticatedError)
})

test('apiRequest accepts an empty 204 response', async () => {
  globalThis.fetch = async () => new Response(null, { status: 204 })

  assert.equal(await apiRequest('/api/tasks/task-1', { method: 'DELETE' }), undefined)
})
