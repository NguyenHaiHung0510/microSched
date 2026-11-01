import { afterEach, expect, test, vi } from 'vitest'
import { mimiDecisionFenceKey, publishAuthoritativeMimiRefusal, publishMimiDecisionAck, readMimiIntent, saveMimiIntent } from '../src/mimi-recovery'
import { recoverMimiReceipt, type MimiChangeSet } from '../src/mimi-api'
import { QueryClient } from '@tanstack/react-query'
import { isMimiSessionCurrent, mimiSessionEpoch, purgeMimiSession } from '../src/mimi-session-boundary'
import { maskPrivateQueries } from '../src/outbox/private-visibility'
import { renderToStaticMarkup } from 'react-dom/server'
import { createElement } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { useMimiFeedbackField, useMimiFeedbackRevision, useRetainedMimiFeedback } from '../src/mimi-feedback-state'

afterEach(() => vi.unstubAllGlobals())
const change = { id: 'review-a', digest: 'digest-a', nonce: 'nonce-a', operation: {
  operation_id: 'operation-a', tool: 'task.create.v1', args: { title: 'Synthetic payload must not persist' },
} } as MimiChangeSet

test.each(['absent', 'digest', 'nonce'])('FE-2: opaque UNKNOWN survives %s snapshot without fabricating a payload', mode => {
  const store = new Map<string, string>()
  vi.stubGlobal('sessionStorage', { getItem: (k: string) => store.get(k), setItem: (k: string, v: string) => store.set(k,v), removeItem: (k: string) => store.delete(k) })
  saveMimiIntent({ conversationId: 'review-conversation', changeSet: change, choice: 'confirm', key: 'original-key' })
  const snapshot = mode === 'absent' ? [] : [{ ...change, [mode]: 'wrong' }]
  const retained = readMimiIntent('review-conversation', snapshot)
  expect(retained?.key).toBe('original-key')
  expect(retained?.changeSet).toMatchObject({ id: change.id, digest: change.digest, nonce: change.nonce })
  expect(JSON.stringify(retained)).not.toContain('Synthetic payload must not persist')
})

test('FE-4 auth purge wins retained positive/negative feedback and fences late writes; PIN lock retains STANDARD drafts', () => {
  const client = new QueryClient()
  const negativeKey = ['mimi-feedback-draft', 'negative-flow', 'c']
  const positiveKey = ['mimi-feedback-draft', 'positive-supplement', 'c', 'm']
  client.setQueryData(negativeKey, { draft: 'Synthetic note', intent: { clientId: 'unknown-key' } })
  client.setQueryData(positiveKey, { text: 'Synthetic positive note' })
  client.setQueryData(['mimi','conversation','c'], { id: 'c' })
  const epoch = mimiSessionEpoch(client)
  maskPrivateQueries(client)
  expect(client.getQueryData(negativeKey)).toBeDefined()
  purgeMimiSession(client)
  expect(client.getQueryData(negativeKey)).toBeUndefined()
  expect(client.getQueryData(positiveKey)).toBeUndefined()
  expect(client.getQueryData(['mimi','conversation','c'])).toBeUndefined()
  expect(isMimiSessionCurrent(client, epoch)).toBe(false)
  const lateWrite = () => { if (isMimiSessionCurrent(client, epoch)) client.setQueryData(negativeKey, { draft: 'late' }) }
  lateWrite()
  expect(client.getQueryData(negativeKey)).toBeUndefined()
  client.clear()
})

test.each(['id', 'digest', 'operation'])('FE-5: receipt recovery rejects a mismatched %s', async mismatch => {
  const saved = { id: 'receipt-a', change_set_id: change.id, digest: change.digest,
    operation_id: change.operation.operation_id, executed_at: '2026-10-29T00:00:00Z', result: {} }
  if (mismatch === 'id') saved.change_set_id = 'other'
  if (mismatch === 'digest') saved.digest = 'other'
  if (mismatch === 'operation') saved.operation_id = 'other'
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(saved), { status: 200 })))
  await expect(recoverMimiReceipt('review-conversation', change, 'original-key')).rejects.toThrow()
})

test('FE-3/5 exact recovery publication creates a remount fence, refuses wrong terminal snapshots and survives stale reads', async () => {
  const client = new QueryClient()
  const intent = { conversationId: 'review-conversation', changeSet: change, choice: 'reject' as const, key: 'original-key' }
  const snapshot = { id: intent.conversationId, messages: [], runs: [], receipts: [], events: [], feedback: [],
    change_sets: [{ ...change, state: 'rejected' }] } as unknown as import('../src/mimi-api').MimiConversation
  for (const bad of [{ ...snapshot, id: 'other' }, { ...snapshot, change_sets: [] },
    { ...snapshot, change_sets: [{ ...change, state: 'rejected', nonce: 'different' }] },
    { ...snapshot, change_sets: [{ ...change, state: 'rejected', digest: 'different' }] }]) {
    expect(await publishAuthoritativeMimiRefusal(client, intent, bad)).toBe(false)
    expect(client.getQueryData(mimiDecisionFenceKey(intent.conversationId))).toBeUndefined()
  }
  expect(await publishAuthoritativeMimiRefusal(client, intent, snapshot)).toBe(true)
  expect(client.getQueryData(mimiDecisionFenceKey(intent.conversationId))).toEqual([{ id: change.id, digest: change.digest, nonce: change.nonce }])
  client.setQueryData(['mimi','conversation',intent.conversationId], { ...snapshot, change_sets: [{ ...change, state: 'pending' }] })
  expect(client.getQueryData(mimiDecisionFenceKey(intent.conversationId))).toBeDefined()
  client.clear()
})

test('FE-4 auth epoch blocks a late decision ACK/refusal before any old cache can be recreated', async () => {
  const client = new QueryClient()
  const epoch = mimiSessionEpoch(client)
  const intent = { conversationId: 'review-conversation', changeSet: change, choice: 'reject' as const, key: 'original-key' }
  purgeMimiSession(client)
  await expect(publishMimiDecisionAck(client, intent, { change_set_id: change.id, state: 'rejected' }, epoch)).rejects.toThrow('session changed')
  expect(await publishAuthoritativeMimiRefusal(client, intent, { id: intent.conversationId, change_sets: [{...change,state:'rejected'}] } as import('../src/mimi-api').MimiConversation, epoch)).toBe(false)
  expect(client.getQueryCache().getAll()).toHaveLength(0)
  client.clear()
})

test('FE-2/4 auth purge retains only the opaque original decision key needed for later explicit recovery', () => {
  const store = new Map<string, string>()
  vi.stubGlobal('sessionStorage', { getItem: (k: string) => store.get(k), setItem: (k: string, v: string) => store.set(k,v), removeItem: (k: string) => store.delete(k) })
  const client = new QueryClient()
  saveMimiIntent({ conversationId: 'review-conversation', changeSet: change, choice: 'confirm', key: 'original-key' })
  purgeMimiSession(client)
  expect(readMimiIntent('review-conversation', [])?.key).toBe('original-key')
  expect([...store.values()].join('')).not.toContain('Synthetic payload must not persist')
  expect(client.getQueryCache().getAll()).toHaveLength(0)
  client.clear()
})

test('FE-4 real retained-field setter and revision cannot recreate feedback after auth purge', () => {
  const client = new QueryClient()
  let lateSet!: (text: string) => void
  let lateRevision!: () => void
  function Capture() {
    useRetainedMimiFeedback('c')
    const [, setDraft] = useMimiFeedbackField('c', 'draft', '')
    const revision = useMimiFeedbackRevision('c')
    lateSet = setDraft
    lateRevision = revision.bump
    return null
  }
  renderToStaticMarkup(createElement(QueryClientProvider, { client }, createElement(Capture)))
  lateSet('Synthetic draft before purge')
  expect(client.getQueryData(['mimi-feedback-draft','negative-flow','c'])).toMatchObject({draft:'Synthetic draft before purge'})
  purgeMimiSession(client)
  lateSet('Late old draft')
  lateRevision()
  expect(client.getQueryCache().getAll()).toHaveLength(0)
  client.clear()
})

test('FE-4 targeted Mimi mutation receipts are purged without clearing unrelated domain mutations', async () => {
  const client = new QueryClient()
  const mimi = client.getMutationCache().build(client, {mutationKey:['mimi','feedback'],mutationFn:async (value:{comment:string})=>value})
  const domain = client.getMutationCache().build(client, {mutationKey:['tasks','fixture'],mutationFn:async()=> 'domain'})
  await mimi.execute({comment:'Synthetic feedback mutation body'})
  await domain.execute(undefined)
  purgeMimiSession(client)
  expect(client.getMutationCache().getAll()).toEqual([domain])
  client.clear()
})
