import assert from 'node:assert/strict'
import { afterEach, test } from 'vitest'

import {
  decideMimiChangeSet,
  fetchCurrentMimiConversation,
  sendMimiMessage,
  type MimiChangeSet,
} from '../src/mimi-api.ts'

const realFetch = globalThis.fetch
afterEach(() => {
  globalThis.fetch = realFetch
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
