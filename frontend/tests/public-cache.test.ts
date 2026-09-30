import { dehydrate, QueryClient } from '@tanstack/react-query'
import type { PersistedClient } from '@tanstack/query-persist-client-core'
import { describe, expect, it } from 'vitest'
import { preserveConfirmedBaseline, sanitizePersistedClient } from '../src/lib/public-cache'

function snapshot(entries: Array<[readonly unknown[], unknown]>): PersistedClient {
  const client = new QueryClient()
  for (const [key, data] of entries) client.setQueryData(key, data)
  return { timestamp: 1, buster: 'fixture', clientState: dehydrate(client) }
}
function serialized(entries: Array<[readonly unknown[], unknown]>) {
  return JSON.stringify(sanitizePersistedClient(snapshot(entries)))
}
const pub = { id: 'public-1', is_private: false, title: 'public' }
const priv = { id: 'private-1', is_private: true, title: 'PRIVATE_CANARY' }

describe('persisted public query safety', () => {
  it('filters the actual notes array shape and retains public notes', () => {
    const result = serialized([[['notes'], [pub, priv]]])
    expect(result).not.toContain('PRIVATE_CANARY')
    expect(result).toContain('public-1')
  })
  it('does not persist a private detail under a public query family', () => {
    const result = serialized([[['tasks', 'detail', 'private-1'], priv]])
    expect(result).not.toContain('PRIVATE_CANARY')
  })
  it('fails closed on missing privacy classification and unsupported query shapes', () => {
    const result = serialized([
      [['tasks', 'all'], { items: [pub, { id: 'unknown', title: 'UNKNOWN_CANARY' }] }],
      [['notes', 'detail', 'opaque'], { body: 'PRIVATE_CANARY' }],
      [['calendar', 'events', 'broken'], { debug: 'UNKNOWN_CANARY' }],
    ])
    expect(result).not.toContain('UNKNOWN_CANARY')
    expect(result).not.toContain('PRIVATE_CANARY')
    expect(result).toContain('public-1')
  })
  it('drops sensitive timeline count and cursor metadata from mixed snapshots', () => {
    const result = sanitizePersistedClient(snapshot([
      [['tasks', 'timeline', 'all'], { items: [pub, priv], counts: { all: 2 }, next_cursor: 'PRIVATE_CURSOR', bucket_cursors: { overdue: 'PRIVATE_CURSOR' } }],
    ]))
    const data = result.clientState.queries[0]?.state.data as Record<string, unknown>
    expect(JSON.stringify(data)).not.toContain('PRIVATE_CANARY')
    expect(JSON.stringify(data)).not.toContain('PRIVATE_CURSOR')
    expect(data.counts).not.toEqual({ all: 2 })
  })
  it('drops session, Mimi and unknown families regardless of key contents', () => {
    const result = serialized([
      [['session'], { private_until: 'PRIVATE_CANARY' }],
      [['mimi', 'conversation'], { content: 'PRIVATE_CANARY' }],
      [['future-domain'], { items: [priv] }],
    ])
    expect(result).not.toContain('PRIVATE_CANARY')
  })
  it('filters entries and subscriptions by explicitly public trackers', () => {
    const result = serialized([
      [['tracker', 'trackers'], { items: [pub, priv] }],
      [['tracker', 'entries'], { items: [{ id: 'e1', tracker_id: pub.id }, { id: 'e2', tracker_id: priv.id, amount: 'PRIVATE_CANARY' }] }],
      [['subscription', 'subscriptions'], { items: [{ id: 's1', tracker_id: pub.id }, { id: 's2', tracker_id: priv.id, name: 'PRIVATE_CANARY' }] }],
    ])
    expect(result).not.toContain('PRIVATE_CANARY')
    expect(result).toContain('e1')
    expect(result).toContain('s1')
  })
})

describe('confirmed baseline while outbox overlays are pending', () => {
  const pending = [{ affected_query_keys: [['tasks']] }]
  it('keeps the last server-confirmed value and allows unrelated cache refresh', () => {
    const baseline = snapshot([[['tasks', 'all'], [pub]], [['notes'], [pub]]])
    const current = snapshot([[['tasks', 'all'], [{ ...pub, title: 'UNCONFIRMED_CANARY' }]], [['notes'], [{ ...pub, title: 'fresh server note' }]]])
    const result = preserveConfirmedBaseline(current, baseline, pending)
    expect(JSON.stringify(result)).not.toContain('UNCONFIRMED_CANARY')
    expect(JSON.stringify(result)).toContain('fresh server note')
    expect(result.clientState.queries.find(q => q.queryKey[0] === 'tasks')?.state.data).toEqual([pub])
  })
  it('does not manufacture a confirmed baseline from a new optimistic query', () => {
    const result = preserveConfirmedBaseline(snapshot([[['tasks', 'open'], [pub]]]), undefined, pending)
    expect(result.clientState.queries).toHaveLength(0)
  })
  it('matches dependencies both above and below a query prefix', () => {
    const baseline = snapshot([[['tasks', 'all'], [pub]]])
    const result = preserveConfirmedBaseline(snapshot([[['tasks', 'all'], []]]), baseline,
      [{ affected_query_keys: [['tasks', 'all', 'a-detail']] }])
    expect(result.clientState.queries[0]?.state.data).toEqual([pub])
  })
  it('cannot resurrect a stale or mismatched baseline', () => {
    const baseline = snapshot([[['tasks', 'all'], [pub]]])
    const current = snapshot([[['tasks', 'all'], []]])
    expect(preserveConfirmedBaseline(current, { ...baseline, buster: 'old' }, pending).clientState.queries).toHaveLength(0)
    expect(preserveConfirmedBaseline({ ...current, timestamp: 8 * 86400000 }, baseline, pending).clientState.queries).toHaveLength(0)
  })
  it('sanitizes private data even when retaining an affected baseline', () => {
    const result = preserveConfirmedBaseline(snapshot([[['tasks', 'completed'], []]]),
      snapshot([[['tasks', 'completed'], [pub, priv]]]), pending)
    expect(JSON.stringify(result)).not.toContain('PRIVATE_CANARY')
    expect(result.clientState.queries[0]?.state.data).toEqual([pub])
  })
})
