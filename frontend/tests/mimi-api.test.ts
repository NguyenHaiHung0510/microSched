import assert from 'node:assert/strict'
import { afterEach, test } from 'vitest'

import {
  decideMimiChangeSet,
  fetchCurrentMimiConversation,
  fetchMimiConversations,
  fetchMimiConfiguration,
  pauseMimiRun,
  saveMimiConfiguration,
  sendMimiMessage,
  streamMimiMessage,
  type MimiChangeSet,
} from '../src/mimi-api.ts'

const realFetch = globalThis.fetch
afterEach(() => {
  globalThis.fetch = realFetch
})

test('conversation history passes the opaque cursor unchanged in a bounded next-page request', async () => {
  const paths: string[] = []
  globalThis.fetch = async (path) => {
    paths.push(String(path))
    return new Response(JSON.stringify({items:[],next_cursor:null}), {status:200,headers:{'Content-Type':'application/json'}})
  }
  await fetchMimiConversations('all')
  await fetchMimiConversations('archived', 'opaque+/cursor=')
  assert.deepEqual(paths, ['/api/mimi/conversations?state=all&limit=50', '/api/mimi/conversations?state=archived&limit=50&cursor=opaque%2B%2Fcursor%3D'])
})

test('Mimi writes carry the scoped CSRF header and stable client generation', async () => {
  let captured: { path: RequestInfo | URL; init?: RequestInit } | undefined
  globalThis.fetch = async (path, init) => {
    captured = { path, init }
    return new Response(JSON.stringify({ messages: [] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  await sendMimiMessage('conversation-1', 'Tạo task thử Mimi', 3, 'client-message-1')

  assert.ok(captured)
  assert.equal(captured.path, '/api/mimi/conversations/conversation-1/messages')
  assert.equal(
    (captured.init?.headers as Record<string, string>)['X-Mimi-CSRF'],
    '1',
  )
  assert.deepEqual(JSON.parse(String(captured.init?.body)), {
    client_id: 'client-message-1',
    content: 'Tạo task thử Mimi',
    expected_generation: 3,
  })
})

test('confirmation binds digest and nonce while idempotency stays in the header', async () => {
  let captured: { path: RequestInfo | URL; init?: RequestInit } | undefined
  globalThis.fetch = async (path, init) => {
    captured = { path, init }
    return new Response(JSON.stringify({ id: 'receipt-1' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }
  const changeSet = {
    id: 'change-1',
    digest: 'a'.repeat(64),
    nonce: '01990000-0000-7000-8000-000000000001',
  } as MimiChangeSet

  await decideMimiChangeSet(changeSet, 'confirm', 'confirm-client-1')

  assert.ok(captured)
  assert.equal(
    (captured.init?.headers as Record<string, string>)['Idempotency-Key'],
    'confirm-client-1',
  )
  assert.deepEqual(JSON.parse(String(captured.init?.body)), {
    digest: changeSet.digest,
    nonce: changeSet.nonce,
    decision: 'confirm',
  })
})

test('reload asks the server for the durable current conversation', async () => {
  let path: RequestInfo | URL | undefined
  globalThis.fetch = async (input) => {
    path = input
    return new Response('null', {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  assert.equal(await fetchCurrentMimiConversation(), null)
  assert.equal(path, '/api/mimi/conversations/current')
})

test('route configuration reads the versioned server profile list', async () => {
  const profiles = Array.from({ length: 4 }, (_, index) => ({
    id: `profile-${index + 1}`,
    label: `Model ${index + 1}`,
    model: `model-${index + 1}`,
    provider: 'local',
    quantization: 'Q4',
    supported_efforts: index === 2 ? [] : ['low', 'high'],
    context_limit: 232_000,
    output_reserve: 32_000,
    available: index !== 3,
    unavailable_reason: index === 3 ? 'Route chưa cấu hình' : null,
  }))
  const configuration = {
    config: { profile_id: 'profile-1', effort: 'high', input_tokens: 100_000 },
    version: 7,
    applies_to: 'next_run',
    active_run_id: 'run-current',
    profiles,
  }
  let path: RequestInfo | URL | undefined
  globalThis.fetch = async (input) => {
    path = input
    return new Response(JSON.stringify(configuration), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  const result = await fetchMimiConfiguration('conversation-1')

  assert.equal(path, '/api/mimi/conversations/conversation-1/configuration')
  assert.equal(result.version, 7)
  assert.equal(result.applies_to, 'next_run')
  assert.equal(result.active_run_id, 'run-current')
  assert.deepEqual(result.profiles, profiles)
})

test('route configuration saves the expected version with the Mimi CSRF header', async () => {
  let captured: { path: RequestInfo | URL; init?: RequestInit } | undefined
  const saved = {
    config: { profile_id: 'profile-2', effort: 'default', input_tokens: 32_000 },
    version: 8,
    applies_to: 'next_run',
    active_run_id: null,
    profiles: [],
  }
  globalThis.fetch = async (path, init) => {
    captured = { path, init }
    return new Response(JSON.stringify(saved), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  const result = await saveMimiConfiguration(
    'conversation-1',
    { profile_id: 'profile-2', effort: 'default', input_tokens: 32_000 },
    7,
  )

  assert.ok(captured)
  assert.equal(captured.path, '/api/mimi/conversations/conversation-1/configuration')
  assert.equal(captured.init?.method, 'PUT')
  assert.equal((captured.init?.headers as Record<string, string>)['X-Mimi-CSRF'], '1')
  assert.deepEqual(JSON.parse(String(captured.init?.body)), {
    expected_version: 7,
    profile_id: 'profile-2',
    effort: 'default',
    input_tokens: 32_000,
  })
  assert.equal(result.version, 8)
})

test('only the explicit preview action sends an exact revision target', async () => {
  const requests: Array<Record<string, unknown>> = []
  globalThis.fetch = async (_path, init) => {
    requests.push(JSON.parse(String(init?.body)) as Record<string, unknown>)
    return new Response(JSON.stringify({ detail: 'test stops before streaming' }), {
      status: 409,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  await assert.rejects(streamMimiMessage('conversation-1', 'sửa preview theo ý này', 2, 'message-1', null, () => {}))
  await assert.rejects(streamMimiMessage(
    'conversation-1',
    'Đổi ngày sang thứ Sáu',
    2,
    'message-2',
    { id: 'change-exact', digest: 'digest-exact' },
    () => {},
  ))

  assert.deepEqual(requests, [
    { client_id: 'message-1', content: 'sửa preview theo ý này', expected_generation: 2, intent: 'auto' },
    {
      client_id: 'message-2',
      content: 'Đổi ngày sang thứ Sáu',
      expected_generation: 2,
      intent: 'revise_pending_preview',
      expected_change_set_id: 'change-exact',
      expected_change_set_digest: 'digest-exact',
    },
  ])
})

test('pause requests a cooperative server pause with Mimi CSRF and preserves acknowledgment semantics', async () => {
  let captured: { path: RequestInfo | URL; init?: RequestInit } | undefined
  const acknowledgment = { run_id: 'run-1', state: 'running', pause_requested: true as const }
  globalThis.fetch = async (path, init) => {
    captured = { path, init }
    return new Response(JSON.stringify(acknowledgment), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  const result = await pauseMimiRun('run-1')

  assert.equal(captured?.path, '/api/mimi/runs/run-1/pause')
  assert.equal(captured?.init?.method, 'POST')
  assert.equal((captured?.init?.headers as Record<string, string>)['X-Mimi-CSRF'], '1')
  assert.equal(result.pause_requested, true)
  assert.equal(result.state, 'running')
})
