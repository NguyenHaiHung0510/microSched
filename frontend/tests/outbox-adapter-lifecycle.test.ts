import { QueryClient } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  adapterFor,
  clearOutboxBaselines,
  hasVerifiedPrivateSession,
  type OperationKind,
} from '@/lib/outbox-adapters'
import type { Json, OutboxRow } from '@/lib/outbox-db'

const { listOutbox } = vi.hoisted(() => ({ listOutbox: vi.fn(async () => []) }))
vi.mock('@/lib/outbox-db', () => ({ listOutbox }))

const ids = {
  task: '0199abc0-0000-7000-8000-000000000011',
  other: '0199abc0-0000-7000-8000-000000000012',
  item: '0199abc0-0000-7000-8000-000000000013',
  note: '0199abc0-0000-7000-8000-000000000014',
  noteItemA: '0199abc0-0000-7000-8000-000000000015',
  noteItemB: '0199abc0-0000-7000-8000-000000000016',
  source: '0199abc0-0000-7000-8000-000000000017',
}

function makeRow(
  kind: OperationKind,
  path: string,
  body: Json | null,
  entityId: string | null,
  parentId: string | null = null,
): OutboxRow {
  const adapter = adapterFor(kind)
  return {
    operation_id: 1,
    operation_kind: kind,
    resource: adapter.resource,
    method: adapter.method,
    path,
    body,
    payload_json: '',
    payload_sha256: '',
    payload_byte_length: 0,
    entity_id: entityId,
    parent_id: parentId,
    requires_private: false,
    idempotency_mode: adapter.idempotencyMode,
    dependency_operation_id: null,
    group_id: null,
    affected_query_keys: adapter.affectedQueryKeys({ path, body, entityId, parentId }) as Json[][],
    state: 'pending',
    attempts: 0,
    next_attempt_at: null,
    created_at: 1,
    last_error_code: null,
  }
}

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

describe('typed outbox adapter lifecycles', () => {
  beforeEach(() => listOutbox.mockResolvedValue([]))

  it('overlays a calendar source with server-shaped defaults, then reconciles the confirmed DTO without invalidating', async () => {
    const queryClient = client()
    queryClient.setQueryData(['calendar', 'sources'], { items: [] })
    const body = { id: ids.source, name: 'Nhà', kind: 'manual' }
    const row = makeRow('calendar_source.create', '/api/calendar/sources', body, ids.source)
    const adapter = adapterFor('calendar_source.create')

    await adapter.optimisticApply(queryClient, row)
    expect(queryClient.getQueryData<{ items: Array<Record<string, unknown>> }>(['calendar', 'sources'])?.items[0])
      .toMatchObject({ id: ids.source, name: 'Nhà', kind: 'manual', is_visible: true, event_count: 0, __outbox_state: 'pending' })

    const server = { ...body, is_visible: false, event_count: 3, color: '#abc', created_at: 'server-time' }
    await adapter.reconcileSuccess(queryClient, row, server)
    expect(queryClient.getQueryData<{ items: Array<Record<string, unknown>> }>(['calendar', 'sources'])?.items)
      .toEqual([server])
    expect(queryClient.getQueryState(['calendar', 'sources'])?.isInvalidated).toBe(false)
    queryClient.clear()
  })

  it('does not synthesize an incomplete entity when an update target is absent from a cached page', async () => {
    const queryClient = client()
    queryClient.setQueryData(['tasks', 'all'], { items: [{ id: ids.other, title: 'Other', items: [] }] })
    const row = makeRow('task.update', `/api/tasks/${ids.task}`, { title: 'Changed' }, ids.task)
    await adapterFor('task.update').optimisticApply(queryClient, row)
    expect(queryClient.getQueryData<{ items: Array<{ id: string }> }>(['tasks', 'all'])?.items)
      .toEqual([{ id: ids.other, title: 'Other', items: [] }])
    queryClient.clear()
  })

  it('does not restore private query rows after the lock boundary while preserving public rollback', async () => {
    const queryClient = client()
    const publicTask = { id: ids.task, title: 'Public before', is_private: false, items: [] }
    const privateTask = { id: ids.other, title: 'Secret', is_private: true, items: [] }
    queryClient.setQueryData(['tasks', 'all'], { items: [publicTask, privateTask], counts: { private_detail: 'secret' }, next_cursor: 'secret-cursor', private_detail: { secret: true } })
    const row = makeRow('task.update', `/api/tasks/${ids.task}`, { title: 'Public pending' }, ids.task)
    const adapter = adapterFor('task.update')

    await adapter.optimisticApply(queryClient, row)
    queryClient.setQueryData(['tasks', 'all'], { items: [
      { ...publicTask, title: 'Public pending', __outbox_state: 'pending' },
    ], private_detail: { secret: true }, next_cursor: 'secret-cursor' })
    clearOutboxBaselines(queryClient)
    await adapter.discardOrRollback(queryClient, row)

    expect(queryClient.getQueryData(['tasks', 'all']))
      .toEqual({ items: [{ id: ids.task, title: 'Public before', is_private: false, items: [] }] })
    queryClient.clear()
  })

  it('permanently forgets old-account baselines on a full purge', async () => {
    const queryClient = client()
    const baseline = { items: [{ id: ids.task, title: 'Account A', is_private: false }] }
    queryClient.setQueryData(['tasks', 'timeline', 'all', '2026-10-01', '2026-10-08'], baseline)
    const row = makeRow('task.update', `/api/tasks/${ids.task}`, { title: 'Pending from A' }, ids.task)
    const adapter = adapterFor('task.update')
    await adapter.optimisticApply(queryClient, row)
    clearOutboxBaselines(queryClient, true)
    queryClient.clear()
    queryClient.setQueryData(['tasks', 'timeline', 'all', '2026-10-01', '2026-10-08'], { items: [] })
    await adapter.discardOrRollback(queryClient, row)
    expect(queryClient.getQueryData(['tasks', 'timeline', 'all', '2026-10-01', '2026-10-08']))
      .toEqual({ items: [] })
    queryClient.clear()
  })

  it('does not retain or restore a private acknowledgement received after lock', async () => {
    vi.stubGlobal('navigator', { onLine: true })
    const queryClient = client()
    queryClient.setQueryData(['tasks', 'timeline', 'all', '2026-10-01', '2026-10-08'], {
      items: [{ id: ids.task, title: 'Public baseline', is_private: false, items: [] }],
    })
    queryClient.setQueryData(['session'], {
      private_until: new Date(Date.now() + 60_000).toISOString(), offline_bootstrap: false,
    })
    const row = makeRow('task.update', `/api/tasks/${ids.task}`, {
      title: 'PRIVATE_ACK_CANARY', is_private: true,
    }, ids.task)
    row.requires_private = true
    const adapter = adapterFor('task.update')
    await adapter.optimisticApply(queryClient, row)
    queryClient.removeQueries({ queryKey: ['session'] })

    await adapter.reconcileSuccess(queryClient, row, {
      id: ids.task, title: 'PRIVATE_ACK_CANARY', is_private: true, items: [],
    })
    expect(JSON.stringify(queryClient.getQueryCache().getAll().map((query) => query.state.data)))
      .not.toContain('PRIVATE_ACK_CANARY')
    clearOutboxBaselines(queryClient, true)
    await adapter.discardOrRollback(queryClient, row)
    expect(JSON.stringify(queryClient.getQueryCache().getAll().map((query) => query.state.data)))
      .not.toContain('PRIVATE_ACK_CANARY')
    queryClient.clear()
    vi.unstubAllGlobals()
  })

  it.each([
    ['task.create', '/api/tasks', ids.task, 'tasks', false],
    ['task.create', '/api/tasks', ids.task, 'tasks', true],
    ['note.create', '/api/notes', ids.note, 'notes', false],
    ['note.create', '/api/notes', ids.note, 'notes', true],
  ] as const)('keeps a late private create acknowledgement out of cache and rollback: %s %s %s %s fullPurge=%s', async (kind, path, id, domain, fullPurge) => {
    vi.stubGlobal('navigator', { onLine: true })
    const queryClient = client()
    const key = [domain, 'all']
    const empty = domain === 'notes' ? [] : { items: [] }
    queryClient.setQueryData(key, empty)
    queryClient.setQueryData(['session'], {
      private_until: new Date(Date.now() + 60_000).toISOString(), offline_bootstrap: false,
    })
    const body = { id, title: 'PRIVATE_CREATE_ACK_CANARY', is_private: true }
    const row = makeRow(kind, path, body, id)
    row.requires_private = true
    const adapter = adapterFor(kind)
    try {
      await adapter.optimisticApply(queryClient, row)
      expect(JSON.stringify(queryClient.getQueryData(key))).toContain('PRIVATE_CREATE_ACK_CANARY')
      queryClient.removeQueries({ queryKey: ['session'] })
      queryClient.setQueryData(key, empty)
      clearOutboxBaselines(queryClient, fullPurge)
      await adapter.reconcileSuccess(queryClient, row, { ...body, items: [] })
      const cachedText = () => JSON.stringify(queryClient.getQueryCache().getAll().map((query) => query.state.data))
      expect(cachedText()).not.toContain('PRIVATE_CREATE_ACK_CANARY')
      await adapter.discardOrRollback(queryClient, row)
      expect(cachedText()).not.toContain('PRIVATE_CREATE_ACK_CANARY')
    } finally {
      queryClient.clear()
      vi.unstubAllGlobals()
    }
  })

  it('classifies public-to-private updates as private and hides cached content without a live session', async () => {
    const queryClient = client()
    queryClient.setQueryData(['tasks', 'all'], { items: [
      { id: ids.task, title: 'Public baseline', is_private: false, items: [] },
    ] })
    const command = adapterFor('task.update').encodeCommand({
      operationKind: 'task.update',
      path: `/api/tasks/${ids.task}`,
      body: { is_private: true, title: 'Sensitive title' },
      entityId: ids.task,
      requiresPrivate: false,
    })
    expect(command.requires_private).toBe(true)
    const row = makeRow('task.update', `/api/tasks/${ids.task}`, command.body, ids.task)
    row.requires_private = false // Simulate an older row written before encoder classification.

    await adapterFor('task.update').optimisticApply(queryClient, row)
    expect(queryClient.getQueryData<{ items: unknown[] }>(['tasks', 'all'])?.items).toEqual([])
    expect(hasVerifiedPrivateSession({ private_until: new Date(Date.now() + 60_000).toISOString() }, Date.now(), false)).toBe(false)
    queryClient.clear()
  })

  it('requires an online, updated, non-bootstrap session with an unexpired private_until', () => {
    const now = Date.now()
    expect(hasVerifiedPrivateSession({ private_until: new Date(now + 60_000).toISOString() }, now, true, now)).toBe(true)
    expect(hasVerifiedPrivateSession({ private_until: new Date(now + 60_000).toISOString(), offline_bootstrap: true }, now, true, now)).toBe(false)
    expect(hasVerifiedPrivateSession({ private_until: new Date(now - 1).toISOString() }, now, true, now)).toBe(false)
    expect(hasVerifiedPrivateSession({ private_until: new Date(now + 60_000).toISOString() }, now, false, now)).toBe(false)
    expect(hasVerifiedPrivateSession({ private_until: new Date(now + 60_000).toISOString() }, 0, true, now)).toBe(false)
  })

  it('rechecks the session after query cancellation so a lock during the await cannot repopulate private cache', async () => {
    vi.stubGlobal('navigator', { onLine: true })
    const queryClient = client()
    queryClient.setQueryData(['session'], {
      private_until: new Date(Date.now() + 60_000).toISOString(),
      offline_bootstrap: false,
    })
    queryClient.setQueryData(['tasks', 'all'], { items: [
      { id: ids.task, title: 'Existing private text', is_private: true, items: [] },
    ] })
    vi.spyOn(queryClient, 'cancelQueries').mockImplementation(async () => {
      queryClient.removeQueries({ queryKey: ['session'] })
    })
    const row = makeRow('task.update', `/api/tasks/${ids.task}`, { title: 'Queued edit' }, ids.task)
    row.requires_private = true

    await adapterFor('task.update').optimisticApply(queryClient, row)
    expect(queryClient.getQueryData<{ items: unknown[] }>(['tasks', 'all'])?.items).toEqual([])
    queryClient.clear()
    vi.unstubAllGlobals()
  })

  it('adds a stable child create to its parent and restores the confirmed baseline on discard', async () => {
    const queryClient = client()
    const baseline = { items: [{ id: ids.task, title: 'Parent', is_private: false, items: [] }] }
    queryClient.setQueryData(['tasks', 'all'], baseline)
    const row = makeRow('task_item.create', `/api/tasks/${ids.task}/items`, { id: ids.item, content: 'Child', position: 0 }, ids.item, ids.task)
    const adapter = adapterFor('task_item.create')

    await adapter.optimisticApply(queryClient, row)
    expect(queryClient.getQueryData<typeof baseline>(['tasks', 'all'])?.items[0].items)
      .toMatchObject([{ id: ids.item, content: 'Child', is_completed: false, __outbox_state: 'pending' }])
    await adapter.discardOrRollback(queryClient, row)
    expect(queryClient.getQueryData(['tasks', 'all'])).toEqual(baseline)
    queryClient.clear()
  })

  it('restores the captured full task DTO and keeps it as baseline after the minimal restore acknowledgement', async () => {
    const queryClient = client()
    queryClient.setQueryData(['tasks', 'all'], { items: [] })
    const task = {
      id: ids.task, title: 'Restored task', body_md: 'Body', status: 'open', priority: 'p2',
      due_precision: 'date', due_on: '2026-10-05', due_at: null, is_private: false,
      pinned: true, items: [{ id: ids.item, content: 'Keep child', is_completed: false, position: 0 }],
      created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-20T00:00:00Z',
    }
    const row = makeRow('task.restore', `/api/tasks/${ids.task}/restore`, null, ids.task)
    Object.assign(row, { optimistic_entity: task })
    const restore = adapterFor('task.restore')
    await restore.optimisticApply(queryClient, row)
    expect(queryClient.getQueryData<{ items: unknown[] }>(['tasks', 'all'])?.items)
      .toMatchObject([{ id: ids.task, title: task.title, items: task.items, __outbox_state: 'pending' }])
    await restore.reconcileSuccess(queryClient, row, { id: ids.task, status: 'restored' })
    expect(queryClient.getQueryData<{ items: Array<Record<string, unknown>> }>(['tasks', 'all'])?.items[0])
      .toEqual(task)

    const laterUpdate = makeRow('task.update', `/api/tasks/${ids.task}`, { title: 'Temporary pending edit' }, ids.task)
    await adapterFor('task.update').optimisticApply(queryClient, laterUpdate)
    await adapterFor('task.update').discardOrRollback(queryClient, laterUpdate)
    expect(queryClient.getQueryData<{ items: Array<Record<string, unknown>> }>(['tasks', 'all'])?.items[0])
      .toEqual(task)
    queryClient.clear()
  })

  it('reconciles an acknowledged task item inside its parent instead of at the task-list root', async () => {
    const queryClient = client()
    const baseline = { items: [{ id: ids.task, title: 'Parent', is_private: false, items: [] }] }
    queryClient.setQueryData(['tasks', 'all'], baseline)
    const row = makeRow('task_item.create', `/api/tasks/${ids.task}/items`, { id: ids.item, content: 'Child', position: 0 }, ids.item, ids.task)
    const adapter = adapterFor('task_item.create')

    await adapter.optimisticApply(queryClient, row)
    await adapter.reconcileSuccess(queryClient, row, {
      id: ids.item, content: 'Child', position: 0, is_completed: false,
      created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z',
    })

    const data = queryClient.getQueryData<typeof baseline>(['tasks', 'all'])
    expect(data?.items).toHaveLength(1)
    expect(data?.items[0].items).toMatchObject([{ id: ids.item, content: 'Child' }])
    expect(data?.items[0].items[0]).not.toHaveProperty('__outbox_state')
    queryClient.clear()
  })

  it('uses the direct NoteItemRead array to reconcile one atomic reorder', async () => {
    const queryClient = client()
    queryClient.setQueryData(['notes'], [{
      id: ids.note,
      is_private: false,
      items: [
        { id: ids.noteItemA, content: 'A', position: 0 },
        { id: ids.noteItemB, content: 'B', position: 1 },
      ],
    }])
    const body = { items: [{ id: ids.noteItemA, position: 1 }, { id: ids.noteItemB, position: 0 }] }
    const row = makeRow('note_item.reorder', `/api/notes/${ids.note}/items/positions`, body, null, ids.note)
    const adapter = adapterFor('note_item.reorder')
    await adapter.optimisticApply(queryClient, row)
    expect(queryClient.getQueryData<Array<{ items: Array<{ id: string }> }>>(['notes'])?.[0].items.map((item) => item.id))
      .toEqual([ids.noteItemB, ids.noteItemA])

    const serverItems = [
      { id: ids.noteItemB, content: 'B', position: 0, created_at: 'b' },
      { id: ids.noteItemA, content: 'A', position: 1, created_at: 'a' },
    ]
    await adapter.reconcileSuccess(queryClient, row, serverItems)
    expect(queryClient.getQueryData<Array<{ items: unknown[] }>>(['notes'])?.[0].items).toEqual(serverItems)
    queryClient.clear()
  })

  it('reconciles a confirmed reminder save only into its active list', async () => {
    const queryClient = client()
    const sourceId = '0199abc0-0000-7000-8000-000000000019'
    queryClient.setQueryData(['reminders', 'active', 'task', sourceId], { items: [] })
    queryClient.setQueryData(['reminders', 'history'], { items: [] })
    const body = {
      id: '0199abc0-0000-7000-8000-000000000022', mode: 'absolute', due_at: '2026-10-02T03:00:00Z', expected_id: null,
      expected_revision: null, expected_source_updated_at: '2026-10-01T01:00:00Z',
    }
    const row = makeRow('reminder.save', `/api/reminders/task/${sourceId}`, body, body.id, sourceId)
    const result = {
      id: ids.item, source_kind: 'task', source_id: sourceId, status: 'pending',
      due_at: body.due_at, revision: 1, is_private: false,
    }
    await adapterFor('reminder.save').reconcileSuccess(queryClient, row, result)
    expect(queryClient.getQueryData<{ items: unknown[] }>(['reminders', 'active', 'task', sourceId])?.items)
      .toEqual([result])
    expect(queryClient.getQueryData(['reminders', 'history'])).toEqual({ items: [] })
    queryClient.clear()
  })

  it('purges a private reminder acknowledgement that arrives after the unlock boundary', async () => {
    vi.stubGlobal('navigator', { onLine: true })
    const queryClient = client()
    const sourceId = '0199abc0-0000-7000-8000-000000000020'
    const key = ['reminders', 'active', 'task', sourceId] as const
    queryClient.setQueryData(key, { items: [] })
    queryClient.setQueryData(['session'], {
      private_until: new Date(Date.now() + 60_000).toISOString(), offline_bootstrap: false,
    })
    const row = makeRow('reminder.save', `/api/reminders/task/${sourceId}`, {
      id: '0199abc0-0000-7000-8000-000000000023', mode: 'absolute', expected_id: null, expected_revision: null,
      expected_source_updated_at: '2026-10-01T01:00:00Z',
    }, '0199abc0-0000-7000-8000-000000000023', sourceId)
    row.requires_private = true
    const adapter = adapterFor('reminder.save')
    await adapter.optimisticApply(queryClient, row)
    queryClient.removeQueries({ queryKey: ['session'] })
    await adapter.reconcileSuccess(queryClient, row, {
      id: ids.item, source_id: sourceId, source_kind: 'task', source_title: 'PRIVATE_REMINDER_CANARY',
      is_private: true, status: 'pending', revision: 1,
    })
    expect(JSON.stringify(queryClient.getQueryData(key))).not.toContain('PRIVATE_REMINDER_CANARY')
    await adapter.discardOrRollback(queryClient, row)
    expect(JSON.stringify(queryClient.getQueryData(key))).not.toContain('PRIVATE_REMINDER_CANARY')
    queryClient.clear()
    vi.unstubAllGlobals()
  })

  it('overlays calendar events into actual 30-day range and numeric month query keys only', async () => {
    const queryClient = client()
    queryClient.setQueryData(['calendar', 'events', '2026-10-01'], { items: [] })
    queryClient.setQueryData(['calendar', 'events', 2026, 10], { items: [] })
    queryClient.setQueryData(['calendar', 'events', '2026-11-20'], { items: [] })
    const body = {
      id: ids.other,
      source_id: ids.source,
      title: 'In range',
      starts_at: '2026-10-15T08:00:00+07:00',
      ends_at: '2026-10-15T09:00:00+07:00',
    }
    const row = makeRow('calendar_event.create', '/api/calendar/events', body, ids.other, ids.source)

    await adapterFor('calendar_event.create').optimisticApply(queryClient, row)
    expect(queryClient.getQueryData<{ items: Array<{ id: string }> }>(['calendar', 'events', '2026-10-01'])?.items)
      .toMatchObject([{ id: ids.other }])
    expect(queryClient.getQueryData<{ items: Array<{ id: string }> }>(['calendar', 'events', 2026, 10])?.items)
      .toMatchObject([{ id: ids.other }])
    expect(queryClient.getQueryData<{ items: unknown[] }>(['calendar', 'events', '2026-11-20'])?.items)
      .toEqual([])
    queryClient.clear()
  })

  it('returns no business result for side-effect renew/import commands', () => {
    expect(adapterFor('subscription.renew').optimisticResponse(makeRow(
      'subscription.renew', `/api/subscriptions/${ids.task}/renew`, { entry_id: ids.item }, ids.task, ids.task,
    ))).toBeNull()
    expect(adapterFor('calendar.import').optimisticResponse(makeRow(
      'calendar.import', `/api/calendar/sources/${ids.source}/import`, { filename: 'a.ics', content: '' }, ids.source, ids.source,
    ))).toBeNull()
  })
})
