import assert from 'node:assert/strict'
import { afterEach, test } from 'vitest'

import { apiRequest, TimeoutError, UnauthenticatedError } from '../src/api.ts'

// Mỗi test dưới đây gán đè `globalThis.fetch` và trước đây không ai trả lại. Một
// file test khác chạy sau trong cùng tiến trình sẽ thừa hưởng con fetch giả của
// test cuối cùng — hỏng vì lý do không liên quan gì tới nó.
const realFetch = globalThis.fetch
afterEach(() => {
  globalThis.fetch = realFetch
})

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

test('every request carries a live abort signal so it can never hang forever', async () => {
  let signal: AbortSignal | null | undefined
  globalThis.fetch = async (_path, init) => {
    signal = init?.signal
    return new Response(null, { status: 204 })
  }

  await apiRequest('/api/tasks', { method: 'POST', body: '{}' })

  // Không có signal thì `fetch` không bao giờ tự bỏ cuộc: request treo ⇒ mutation
  // kẹt `isPending` vĩnh viễn ⇒ nút đứng ở "Đang thêm…" mà không lỗi, không retry,
  // không đường thoát ngoài tải lại trang. Đừng gỡ dòng này.
  assert.ok(signal instanceof AbortSignal, 'apiRequest phải luôn gắn AbortSignal')
  // Signal đã abort sẵn cũng "truthy" — hỏi thêm câu này để phép khẳng định trên
  // không xanh nhờ một vật thể bất kỳ.
  assert.equal(signal.aborted, false)
})

test('a stalled request surfaces as TimeoutError, not a silent hang', async () => {
  globalThis.fetch = async () => {
    throw new DOMException('The operation timed out.', 'TimeoutError')
  }

  await assert.rejects(apiRequest('/api/tasks'), TimeoutError)
})

test('a caller-supplied signal is composed with the timeout, not substituted for it', async () => {
  const controller = new AbortController()
  let seen: AbortSignal | null | undefined
  globalThis.fetch = async (_path, init) => {
    seen = init?.signal
    return new Response(null, { status: 204 })
  }

  await apiRequest('/api/tasks', { method: 'DELETE', signal: controller.signal })

  // Bản đầu của 008i viết `init.signal ?? AbortSignal.timeout(...)` và test cũ
  // khẳng định `seen === controller.signal` — tức là ĐÓNG ĐINH cái lỗ: người gọi
  // mang signal riêng thì hạn 20 giây biến mất, và request đó lại được phép treo
  // vĩnh viễn. Signal đưa cho fetch phải là signal GHÉP, không phải signal gốc.
  assert.ok(seen instanceof AbortSignal)
  assert.notEqual(seen, controller.signal)

  // Và ghép rồi thì vẫn phải nghe người gọi, kèm nguyên `reason`.
  const reason = new Error('người gọi tự huỷ')
  controller.abort(reason)
  assert.equal(seen.aborted, true)
  assert.equal(seen.reason, reason)
})

test('an already-aborted caller signal aborts the request immediately', async () => {
  let seen: AbortSignal | null | undefined
  globalThis.fetch = async (_path, init) => {
    seen = init?.signal
    return new Response(null, { status: 204 })
  }

  // Nhánh `source.aborted` chạy TRƯỚC khi kịp gắn listener; không có nhánh đó thì
  // một signal đã abort từ trước sẽ không bao giờ kích hoạt `abort` lần nữa và
  // request vẫn đi ra mạng như thường.
  await apiRequest('/api/tasks', { signal: AbortSignal.abort(new Error('quá muộn')) })

  assert.ok(seen instanceof AbortSignal)
  assert.equal(seen.aborted, true)
})
