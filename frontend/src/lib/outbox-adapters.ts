import type { QueryClient, QueryKey } from '@tanstack/react-query'

import type { Json, OutboxRow } from '@/lib/outbox-db'

export type CommandInput = {
  path: string
  body?: Json | null
  entityId?: string | null
  parentId?: string | null
  requiresPrivate?: boolean
  dependencyOperationId?: number | null
  groupId?: string | null
}

export type OutboxAdapter = {
  method: OutboxRow['method']
  resource: string
  idempotencyMode: OutboxRow['idempotency_mode']
  affectedQueryKeys(input: CommandInput): QueryKey[]
  optimisticApply(client: QueryClient, row: OutboxRow): Promise<void>
  reconcileSuccess(client: QueryClient, row: OutboxRow, response: unknown): Promise<void>
  discardOrRollback(client: QueryClient, row: OutboxRow): Promise<void>
  optimisticResponse(row: OutboxRow): unknown
}

const resourceKeys: Record<string, QueryKey[]> = {
  task: [['tasks'], ['calendar']],
  task_item: [['tasks'], ['calendar']],
  note: [['notes']],
  note_item: [['notes']],
  calendar_source: [['calendar']],
  calendar_event: [['calendar']],
  day_annotation: [['calendar']],
  tracker_group: [['tracker']],
  tracker: [['tracker'], ['subscription']],
  entry: [['tracker']],
  subscription: [['subscription'], ['tracker']],
  setting: [['subscription'], ['tracker']],
  reminder: [['tracker']],
}

type Entity = Record<string, unknown> & { id?: unknown }

function isEnvelope(value: unknown): value is { items: Entity[] } {
  return Boolean(
    value && typeof value === 'object' && 'items' in value && Array.isArray(value.items),
  )
}

function mapEnvelopes(client: QueryClient, keys: QueryKey[], apply: (items: Entity[]) => Entity[]) {
  for (const key of keys) {
    client.setQueriesData({ queryKey: key }, (old) =>
      isEnvelope(old) ? { ...old, items: apply(old.items) } : old,
    )
  }
}

function optimisticEntity(row: OutboxRow) {
  const body = row.body && !Array.isArray(row.body) && typeof row.body === 'object' ? row.body : {}
  return {
    id: row.entity_id,
    ...body,
    __outbox_state: row.state === 'failed' ? 'failed' : 'pending',
  }
}

function genericAdapter(
  method: OutboxRow['method'],
  resource: string,
  idempotencyMode: OutboxRow['idempotency_mode'],
): OutboxAdapter {
  const keys = resourceKeys[resource] ?? []
  return {
    method,
    resource,
    idempotencyMode,
    affectedQueryKeys: () => keys,
    async optimisticApply(client, row) {
      await Promise.all(keys.map((queryKey) => client.cancelQueries({ queryKey })))
      if (!row.entity_id) return
      mapEnvelopes(client, keys, (items) => {
        if (method === 'DELETE') return items.filter((item) => item.id !== row.entity_id)
        const next = optimisticEntity(row)
        const found = items.some((item) => item.id === row.entity_id)
        return found
          ? items.map((item) => (item.id === row.entity_id ? { ...item, ...next } : item))
          : method === 'POST'
            ? [...items, next]
            : items
      })
    },
    async reconcileSuccess(client, row, response) {
      if (row.entity_id && response && typeof response === 'object') {
        const replacement = response as Entity
        mapEnvelopes(client, keys, (items) =>
          items.map((item) => (item.id === row.entity_id ? replacement : item)),
        )
      }
      await Promise.all(keys.map((queryKey) => client.invalidateQueries({ queryKey })))
    },
    async discardOrRollback(client) {
      await Promise.all(keys.map((queryKey) => client.invalidateQueries({ queryKey })))
    },
    optimisticResponse: (row) => optimisticEntity(row),
  }
}

const definitions = {
  'task.create': ['POST', 'task', 'client_uuid'],
  'task.update': ['PATCH', 'task', 'absolute'],
  'task.delete': ['DELETE', 'task', 'postcondition'],
  'task.restore': ['POST', 'task', 'absolute'],
  'task_item.create': ['POST', 'task_item', 'client_uuid'],
  'task_item.update': ['PATCH', 'task_item', 'absolute'],
  'task_item.delete': ['DELETE', 'task_item', 'postcondition'],
  'note.create': ['POST', 'note', 'client_uuid'],
  'note.update': ['PATCH', 'note', 'absolute'],
  'note.delete': ['DELETE', 'note', 'postcondition'],
  'note.restore': ['POST', 'note', 'absolute'],
  'note_item.create': ['POST', 'note_item', 'client_uuid'],
  'note_item.update': ['PATCH', 'note_item', 'absolute'],
  'note_item.delete': ['DELETE', 'note_item', 'postcondition'],
  'note_item.reorder': ['PATCH', 'note_item', 'absolute'],
  'calendar_source.create': ['POST', 'calendar_source', 'client_uuid'],
  'calendar_source.update': ['PATCH', 'calendar_source', 'absolute'],
  'calendar_source.delete': ['DELETE', 'calendar_source', 'postcondition'],
  'calendar.import': ['POST', 'calendar_source', 'side_effect'],
  'calendar_event.create': ['POST', 'calendar_event', 'client_uuid'],
  'calendar_event.update': ['PATCH', 'calendar_event', 'absolute'],
  'calendar_event.delete': ['DELETE', 'calendar_event', 'postcondition'],
  'day_annotation.create': ['POST', 'day_annotation', 'client_uuid'],
  'day_annotation.update': ['PATCH', 'day_annotation', 'absolute'],
  'day_annotation.delete': ['DELETE', 'day_annotation', 'postcondition'],
  'tracker_group.create': ['POST', 'tracker_group', 'client_uuid'],
  'tracker_group.update': ['PATCH', 'tracker_group', 'absolute'],
  'tracker_group.delete': ['DELETE', 'tracker_group', 'postcondition'],
  'tracker.create': ['POST', 'tracker', 'client_uuid'],
  'tracker.update': ['PATCH', 'tracker', 'absolute'],
  'tracker.archive': ['DELETE', 'tracker', 'postcondition'],
  'tracker.restore': ['POST', 'tracker', 'absolute'],
  'entry.create': ['POST', 'entry', 'client_uuid'],
  'entry.update': ['PATCH', 'entry', 'absolute'],
  'entry.delete': ['DELETE', 'entry', 'postcondition'],
  'entry.restore': ['POST', 'entry', 'absolute'],
  'subscription.create': ['POST', 'subscription', 'client_uuid'],
  'subscription.update': ['PATCH', 'subscription', 'absolute'],
  'subscription.cancel': ['POST', 'subscription', 'absolute'],
  'subscription.uncancel': ['POST', 'subscription', 'absolute'],
  'subscription.renew': ['POST', 'subscription', 'side_effect'],
  'subscription.delete': ['DELETE', 'subscription', 'postcondition'],
  'subscription.restore': ['POST', 'subscription', 'absolute'],
  'setting.show_list_price.update': ['PATCH', 'setting', 'absolute'],
  'setting.subscription_expiry_lead_days.update': ['PATCH', 'setting', 'absolute'],
  'reminder.confirm': ['POST', 'reminder', 'side_effect'],
} as const satisfies Record<
  string,
  readonly [OutboxRow['method'], string, OutboxRow['idempotency_mode']]
>

export type OperationKind = keyof typeof definitions
export const outboxAdapters = Object.fromEntries(
  Object.entries(definitions).map(([kind, [method, resource, mode]]) => [
    kind,
    genericAdapter(method, resource, mode),
  ]),
) as Record<OperationKind, OutboxAdapter>

export function adapterFor(kind: string): OutboxAdapter {
  const adapter = outboxAdapters[kind as OperationKind]
  if (!adapter) throw new Error(`Unknown outbox operation: ${kind}`)
  return adapter
}
