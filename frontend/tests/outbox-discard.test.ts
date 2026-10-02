import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { OutboxRow } from '@/lib/outbox-db'

const fixture = vi.hoisted(() => ({ rows: [] as OutboxRow[], transaction: vi.fn(), deleted: vi.fn() }))
vi.mock('dexie', () => ({ default: class {
  outbox = {
    orderBy: () => ({ toArray: async () => fixture.rows }),
    toArray: async () => fixture.rows,
    bulkDelete: async (ids: number[]) => { fixture.deleted(ids); fixture.rows = fixture.rows.filter((row) => !ids.includes(row.operation_id!)) },
  }
  version() { return { stores: () => undefined } }
  async open() {}
  async transaction(_mode: string, _table: unknown, action: () => Promise<unknown>) { fixture.transaction(); return action() }
} }))
import { discardOutboxTree } from '@/lib/outbox-db'

function row(id: number, state: OutboxRow['state'], attempts = 0, dependency: number | null = null): OutboxRow {
  return { operation_id: id, operation_kind: 'task.create', resource: 'task', method: 'POST', path: '/api/tasks', body: { id: String(id) }, payload_json: '{}', payload_sha256: 'digest', payload_byte_length: 2, entity_id: String(id), parent_id: null, requires_private: false, idempotency_mode: 'client_uuid', dependency_operation_id: dependency, group_id: null, affected_query_keys: [['tasks']], state, attempts, next_attempt_at: null, created_at: 0, last_error_code: state === 'failed' ? 'HTTP_422' : null }
}
beforeEach(() => {
  fixture.rows = []; fixture.deleted.mockClear(); fixture.transaction.mockClear()
  vi.stubGlobal('window', { dispatchEvent: vi.fn() })
  vi.stubGlobal('BroadcastChannel', class { postMessage() {} close() {} })
})
describe('destructive queue discard', () => {
  it.each(['pending', 'outcome_unknown', 'auth_hold', 'private_hold'] as const)('retains a %s root without rolling back its possible server outcome', async (state) => {
    fixture.rows = [row(1, state, 1), row(2, 'pending', 0, 1)]
    await expect(discardOutboxTree(1)).rejects.toThrow()
    expect(fixture.deleted).not.toHaveBeenCalled()
    expect(fixture.rows).toHaveLength(2)
  })
  it('retains the complete tree if any descendant was dispatched without a known rejection', async () => {
    fixture.rows = [row(1, 'failed', 1), row(2, 'suppressed', 1, 1)]
    await expect(discardOutboxTree(1)).rejects.toThrow()
    expect(fixture.deleted).not.toHaveBeenCalled()
  })
  it('does not call a previously dispatched unrecognized command a known server rejection', async () => {
    fixture.rows = [{ ...row(1, 'failed', 1), last_error_code: 'UNKNOWN_OPERATION' }]
    await expect(discardOutboxTree(1)).rejects.toThrow()
    expect(fixture.deleted).not.toHaveBeenCalled()
  })
  it('discards a rejected parent and its never-dispatched descendants atomically, preserving independent rows', async () => {
    fixture.rows = [row(1, 'failed', 1), row(2, 'suppressed', 0, 1), row(3, 'suppressed', 0, 2), row(4, 'pending')]
    expect((await discardOutboxTree(1)).map((item) => item.operation_id)).toEqual([1, 2, 3])
    expect(fixture.transaction).toHaveBeenCalledOnce()
    expect(fixture.rows.map((item) => item.operation_id)).toEqual([4])
  })
})
