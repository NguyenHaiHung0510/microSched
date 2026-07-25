import assert from 'node:assert/strict'
import { test } from 'vitest'

import { apiRequest, TimeoutError, UnauthenticatedError } from '../src/api.ts'

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

test('every request carries an abort signal so it can never hang forever', async () => {
  let signal: AbortSignal | null | undefined
  globalThis.fetch = async (_path, init) => {
    signal = init?.signal
    return new Response(null, { status: 204 })
  }

  await apiRequest('/api/tasks', { method: 'POST', body: '{}' })

  // Không có signal thì `fetch` không bao giờ tự bỏ cuộc: request treo ⇒ mutation
  // kẹt `isPending` vĩnh viễn ⇒ nút đứng ở "Đang thêm…" mà không lỗi, không retry,
  // không đường thoát ngoài tải lại trang. Đừng gỡ dòng này.
  assert.ok(signal, 'apiRequest phải luôn gắn AbortSignal')
})

test('a stalled request surfaces as TimeoutError, not a silent hang', async () => {
  globalThis.fetch = async () => {
    throw new DOMException('The operation timed out.', 'TimeoutError')
  }

  await assert.rejects(apiRequest('/api/tasks'), TimeoutError)
})

test('a caller-supplied signal wins over the default timeout', async () => {
  const controller = new AbortController()
  let seen: AbortSignal | null | undefined
  globalThis.fetch = async (_path, init) => {
    seen = init?.signal
    return new Response(null, { status: 204 })
  }

  await apiRequest('/api/tasks', { method: 'DELETE', signal: controller.signal })

  assert.equal(seen, controller.signal)
})
