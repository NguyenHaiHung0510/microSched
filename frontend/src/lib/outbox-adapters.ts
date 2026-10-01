import type { QueryClient, QueryKey } from '@tanstack/react-query'

import { listOutbox, restoreCancelledOutbox, type Json, type OutboxRow } from '@/lib/outbox-db'
import { sanitizePersistedClient } from '@/lib/public-cache'
import type { PersistedClient } from '@tanstack/query-persist-client-core'

export type CommandInput = {
  path: string
  body?: Json | null
  optimisticEntity?: Json
  entityId?: string | null
  parentId?: string | null
  requiresPrivate?: boolean
  dependencyOperationId?: number | null
  groupId?: string | null
}
type DomainHttpMethod = OutboxRow['method'] | 'PUT'

/**
 * Domain-owned command metadata. The queue core adds runtime fields (timestamps,
 * state and payload receipt) after this value is produced.
 */
export type EncodedCommand = {
  operation_kind: OperationKind
  resource: string
  method: DomainHttpMethod
  path: string
  body: Json | null
  optimistic_entity?: Json
  entity_id: string | null
  parent_id: string | null
  requires_private: boolean
  idempotency_mode: OutboxRow['idempotency_mode']
  dependency_operation_id: number | null
  group_id: string | null
  affected_query_keys: QueryKey[]
}

export type DomainCommandInput = CommandInput & {
  operationKind: OperationKind
}

export type OutboxAdapter = {
  method: DomainHttpMethod
  resource: string
  idempotencyMode: OutboxRow['idempotency_mode']
  affectedQueryKeys(input: CommandInput): QueryKey[]
  optimisticApply(client: QueryClient, row: OutboxRow): Promise<void>
  reconcileSuccess(client: QueryClient, row: OutboxRow, response: unknown): Promise<void>
  discardOrRollback(client: QueryClient, row: OutboxRow): Promise<void>
  optimisticResponse(row: OutboxRow): unknown
  encodeCommand(input: DomainCommandInput): EncodedCommand
}

type Entity = Record<string, unknown> & { id?: unknown }
type Resource = 'task' | 'task_item' | 'note' | 'note_item' | 'calendar_source' |
  'calendar_event' | 'day_annotation' | 'tracker_group' | 'tracker' | 'entry' |
  'subscription' | 'setting' | 'reminder'
type AdapterSpec = {
  method: DomainHttpMethod
  resource: Resource
  idempotencyMode: OutboxRow['idempotency_mode']
  keys: (input: CommandInput) => QueryKey[]
  route: (input: CommandInput) => string
  /** Data shape returned synchronously to the screen while this command is queued. */
  optimisticDto: (input: CommandInput) => Entity | null
}

const objectBody = (body: Json | null | undefined): Record<string, Json> =>
  body !== null && !Array.isArray(body) && typeof body === 'object' ? body : {}
const idFrom = (input: CommandInput) => {
  const bodyId = objectBody(input.body).id
  return input.entityId ?? (typeof bodyId === 'string' ? bodyId : null)
}
const dto = (input: CommandInput, defaults: Record<string, Json> = {}): Entity | null => {
  const id = idFrom(input)
  if (!id) return null
  return { id, ...defaults, ...objectBody(input.body), __outbox_state: 'pending' }
}
const noDto: AdapterSpec['optimisticDto'] = (input) => {
  void input
  return null
}
export function requiresPrivateRow(row: Pick<OutboxRow, 'requires_private' | 'body'>): boolean {
  return row.requires_private || objectBody(row.body).is_private === true
}
const isRestoreOperation = (kind: OperationKind) =>
  kind === 'task.restore' || kind === 'note.restore' || kind === 'tracker.restore' ||
  kind === 'entry.restore' || kind === 'subscription.restore'
const taskKeys = () => [['tasks'], ['calendar', 'tasks']] as QueryKey[]
const noteKeys = () => [['notes']] as QueryKey[]
const calendarSourceKeys = () => [['calendar', 'sources']] as QueryKey[]
const calendarEventKeys = () => [['calendar', 'events']] as QueryKey[]
const annotationKeys = () => [['calendar', 'annotations']] as QueryKey[]
const trackerGroupKeys = () => [['tracker', 'groups']] as QueryKey[]
const trackerKeys = () => [['tracker', 'trackers']] as QueryKey[]
const entryKeys = () => [['tracker', 'entries']] as QueryKey[]
const subscriptionKeys = () => [['subscription', 'subscriptions']] as QueryKey[]
const settingsKeys = () => [['subscription', 'settings']] as QueryKey[]
const reminderKeys = () => [['reminders']] as QueryKey[]

/**
 * Each operation declares its route family, DTO defaults and query surface.
 * The DTOs intentionally contain the server's required defaults so queued creates
 * render like domain objects while retaining an explicit pending marker.
 */
const definitions = {
  'task.create': { method:'POST', resource:'task', idempotencyMode:'client_uuid', route:()=>'/api/tasks', keys:taskKeys, optimisticDto:(i:CommandInput)=>dto(i,{status:'open',items:[],pinned:false,is_private:false,created_at:null,updated_at:null}) },
  'task.update': { method:'PATCH', resource:'task', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:taskKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'task.delete': { method:'DELETE', resource:'task', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:taskKeys, optimisticDto:noDto },
  'task.restore': { method:'POST', resource:'task', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:taskKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'task_item.create': { method:'POST', resource:'task_item', idempotencyMode:'client_uuid', route:(i:CommandInput)=>i.path, keys:taskKeys, optimisticDto:(i:CommandInput)=>dto(i,{is_completed:false,created_at:null,updated_at:null}) },
  'task_item.update': { method:'PATCH', resource:'task_item', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:taskKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'task_item.delete': { method:'DELETE', resource:'task_item', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:taskKeys, optimisticDto:noDto },
  'note.create': { method:'POST', resource:'note', idempotencyMode:'client_uuid', route:()=>'/api/notes', keys:noteKeys, optimisticDto:(i:CommandInput)=>dto(i,{items:[],is_private:false,pinned:false,created_at:null,updated_at:null}) },
  'note.update': { method:'PATCH', resource:'note', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:noteKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'note.delete': { method:'DELETE', resource:'note', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:noteKeys, optimisticDto:noDto },
  'note.restore': { method:'POST', resource:'note', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:noteKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'note_item.create': { method:'POST', resource:'note_item', idempotencyMode:'client_uuid', route:(i:CommandInput)=>i.path, keys:noteKeys, optimisticDto:(i:CommandInput)=>dto(i,{is_completed:false,created_at:null,updated_at:null}) },
  'note_item.update': { method:'PATCH', resource:'note_item', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:noteKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'note_item.delete': { method:'DELETE', resource:'note_item', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:noteKeys, optimisticDto:noDto },
  'note_item.reorder': { method:'PATCH', resource:'note_item', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:noteKeys, optimisticDto:noDto },
  'calendar_source.create': { method:'POST', resource:'calendar_source', idempotencyMode:'client_uuid', route:()=>'/api/calendar/sources', keys:calendarSourceKeys, optimisticDto:(i:CommandInput)=>dto(i,{color:null,is_visible:true,event_count:0,created_at:null,updated_at:null}) },
  'calendar_source.update': { method:'PATCH', resource:'calendar_source', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:calendarSourceKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'calendar_source.delete': { method:'DELETE', resource:'calendar_source', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:calendarSourceKeys, optimisticDto:noDto },
  'calendar.import': { method:'POST', resource:'calendar_source', idempotencyMode:'side_effect', route:(i:CommandInput)=>i.path, keys:calendarEventKeys, optimisticDto:noDto },
  'calendar_event.create': { method:'POST', resource:'calendar_event', idempotencyMode:'client_uuid', route:()=>'/api/calendar/events', keys:calendarEventKeys, optimisticDto:(i:CommandInput)=>dto(i,{all_day:false,location:null,description_md:null,created_at:null,updated_at:null}) },
  'calendar_event.update': { method:'PATCH', resource:'calendar_event', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:calendarEventKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'calendar_event.delete': { method:'DELETE', resource:'calendar_event', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:calendarEventKeys, optimisticDto:noDto },
  'day_annotation.create': { method:'POST', resource:'day_annotation', idempotencyMode:'client_uuid', route:()=>'/api/calendar/annotations', keys:annotationKeys, optimisticDto:(i:CommandInput)=>dto(i,{note_md:null,color:null,is_private:false,created_at:null,updated_at:null}) },
  'day_annotation.update': { method:'PATCH', resource:'day_annotation', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:annotationKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'day_annotation.delete': { method:'DELETE', resource:'day_annotation', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:annotationKeys, optimisticDto:noDto },
  'tracker_group.create': { method:'POST', resource:'tracker_group', idempotencyMode:'client_uuid', route:()=>'/api/tracker/groups', keys:trackerGroupKeys, optimisticDto:(i:CommandInput)=>dto(i,{color:null,tracker_count:0,created_at:null,updated_at:null}) },
  'tracker_group.update': { method:'PATCH', resource:'tracker_group', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:trackerGroupKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'tracker_group.delete': { method:'DELETE', resource:'tracker_group', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:trackerGroupKeys, optimisticDto:noDto },
  'tracker.create': { method:'POST', resource:'tracker', idempotencyMode:'client_uuid', route:()=>'/api/tracker/trackers', keys:trackerKeys, optimisticDto:(i:CommandInput)=>dto(i,{color:null,group_id:null,unit:null,reminder_time:null,reminder_text:null,reminder_mode:null,reminder_interval_days:null,reminder_action:null,last_entry_at:null,next_reminder_at:null,entry_count_30d:0,created_at:null,updated_at:null}) },
  'tracker.update': { method:'PATCH', resource:'tracker', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:trackerKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'tracker.archive': { method:'DELETE', resource:'tracker', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:trackerKeys, optimisticDto:noDto },
  'tracker.restore': { method:'POST', resource:'tracker', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:trackerKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'entry.create': { method:'POST', resource:'entry', idempotencyMode:'client_uuid', route:()=>'/api/tracker/entries', keys:entryKeys, optimisticDto:(i:CommandInput)=>dto(i,{occurred_at:null,quantity:null,amount:null,list_amount:null,note_md:null,created_at:null,updated_at:null}) },
  'entry.update': { method:'PATCH', resource:'entry', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:entryKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'entry.delete': { method:'DELETE', resource:'entry', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:entryKeys, optimisticDto:noDto },
  'entry.restore': { method:'POST', resource:'entry', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:entryKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'subscription.create': { method:'POST', resource:'subscription', idempotencyMode:'client_uuid', route:()=>'/api/subscriptions', keys:subscriptionKeys, optimisticDto:(i:CommandInput)=>dto(i,{list_amount:null,canceled_at:null,note_md:null,deleted_at:null,created_at:null,updated_at:null,status:'active',days_left:0,monthly_amount:null,corrupted:false}) },
  'subscription.update': { method:'PATCH', resource:'subscription', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:subscriptionKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'subscription.cancel': { method:'POST', resource:'subscription', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:subscriptionKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'subscription.uncancel': { method:'POST', resource:'subscription', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:subscriptionKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'subscription.renew': { method:'POST', resource:'subscription', idempotencyMode:'side_effect', route:(i:CommandInput)=>i.path, keys:subscriptionKeys, optimisticDto:noDto },
  'subscription.delete': { method:'DELETE', resource:'subscription', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:subscriptionKeys, optimisticDto:noDto },
  'subscription.restore': { method:'POST', resource:'subscription', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:subscriptionKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'setting.show_list_price.update': { method:'PATCH', resource:'setting', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:settingsKeys, optimisticDto:(i:CommandInput)=>({key:'show_list_price',...objectBody(i.body),__outbox_state:'pending'}) },
  'setting.subscription_expiry_lead_days.update': { method:'PATCH', resource:'setting', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:settingsKeys, optimisticDto:(i:CommandInput)=>({key:'subscription_expiry_lead_days',...objectBody(i.body),__outbox_state:'pending'}) },
  // This is the existing scheduled tracker-reminder action, not Mimi's
  // confirmation surface. Its entry_id is created at the screen before enqueue.
  'reminder.confirm': { method:'POST', resource:'reminder', idempotencyMode:'side_effect', route:(i:CommandInput)=>i.path, keys:trackerKeys, optimisticDto:noDto },
  'reminder.save': { method:'PUT', resource:'reminder', idempotencyMode:'client_uuid', route:(i:CommandInput)=>i.path, keys:reminderKeys, optimisticDto:noDto },
  'reminder.cancel': { method:'DELETE', resource:'reminder', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:reminderKeys, optimisticDto:noDto },
} as const satisfies Record<string, AdapterSpec>

type CacheSnapshot = Array<[QueryKey, unknown]>
const confirmedBaselines = new WeakMap<QueryClient, Map<string, CacheSnapshot>>()
const keyId = (key: QueryKey) => JSON.stringify(key)
const record = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null

function queryKeyStartsWith(queryKey: QueryKey, prefix: QueryKey) {
  return prefix.length <= queryKey.length && prefix.every((part, index) => keyId([part]) === keyId([queryKey[index]]))
}

function omitPrivateTargets(snapshot: CacheSnapshot, row?: OutboxRow): CacheSnapshot {
  if (!row || !requiresPrivateRow(row)) return snapshot
  const ids = new Set<string>()
  if (row.entity_id) ids.add(row.entity_id)
  if (row.parent_id && ['task_item', 'note_item', 'entry', 'subscription'].includes(row.resource)) ids.add(row.parent_id)
  return snapshot.map(([key, value]) => {
    const filter = (items: unknown[]) => items.filter((item) => {
      const entity = record(item)
      return !entity || typeof entity.id !== 'string' || !ids.has(entity.id)
    })
    if (Array.isArray(value)) return [key, filter(value)]
    const envelope = record(value)
    if (envelope && Array.isArray(envelope.items)) return [key, { ...envelope, items: filter(envelope.items) }]
    return [key, value]
  })
}

/** Use the same typed public allowlist as persistence; baseline code owns no second privacy policy. */
function sanitizedPublicSnapshot(client: QueryClient, overrides: CacheSnapshot = [], row?: OutboxRow): CacheSnapshot {
  const values = new Map<string, [QueryKey, unknown]>()
  for (const query of client.getQueryCache().getAll()) {
    values.set(keyId(query.queryKey), [query.queryKey, query.state.data])
  }
  for (const [queryKey, value] of omitPrivateTargets(overrides, row)) values.set(keyId(queryKey), [queryKey, value])
  const persisted = {
    timestamp: Date.now(),
    buster: 'outbox-public-baseline',
    clientState: {
      mutations: [],
      queries: [...values.values()].map(([queryKey, data]) => ({
        queryKey,
        state: { status: 'success', data, error: null, fetchFailureReason: null, fetchMeta: null },
      })),
    },
  } as unknown as PersistedClient
  const sanitized = sanitizePersistedClient(persisted)
  return sanitized.clientState.queries.map((query) => [query.queryKey as QueryKey, query.state.data])
}

/** Called by the T1-owned public-cache purge before lock/logout/TTL eviction. */
export function clearOutboxBaselines(client: QueryClient, full = false) {
  const byKey = confirmedBaselines.get(client)
  if (full) {
    confirmedBaselines.delete(client)
    return
  }
  if (!byKey) return
  const originals = [...byKey.values()].flat()
  const sanitized = sanitizedPublicSnapshot(client, originals)
  for (const key of byKey.keys()) {
    byKey.set(key, sanitized.filter(([queryKey]) => queryKeyStartsWith(queryKey, JSON.parse(key) as QueryKey)))
  }
}

function captureBaseline(client: QueryClient, keys: QueryKey[], row?: OutboxRow) {
  let byKey = confirmedBaselines.get(client)
  if (!byKey) {
    byKey = new Map()
    confirmedBaselines.set(client, byKey)
  }
  for (const key of keys) {
    const id = keyId(key)
    if (!byKey.has(id)) {
      const snapshot = sanitizedPublicSnapshot(client, [], row).filter(([queryKey]) => queryKeyStartsWith(queryKey, key))
      byKey.set(id, snapshot)
    }
  }
}

function restoreBaseline(client: QueryClient, keys: QueryKey[]) {
  const byKey = confirmedBaselines.get(client)
  if (!byKey) return
  for (const key of keys) {
    const snapshot = byKey.get(keyId(key))
    if (!snapshot) continue
    for (const [queryKey, value] of snapshot) client.setQueryData(queryKey, value)
  }
}

function mutateEnvelope(client: QueryClient, key: QueryKey, change: (items: Entity[]) => Entity[]) {
  client.setQueriesData({ queryKey: key }, (old) => {
    const value = record(old)
    if (!value || !Array.isArray(value.items)) return old
    return { ...value, items: change(value.items as Entity[]) }
  })
}

function mutateNoteList(client: QueryClient, change: (items: Entity[]) => Entity[]) {
  client.setQueriesData({ queryKey: ['notes'] }, (old) =>
    Array.isArray(old) ? change(old as Entity[]) : old,
  )
}

function mutateCalendarRangeQueries(client: QueryClient, keyPrefix: QueryKey, row: OutboxRow, model: Entity | null, action: 'upsert' | 'update' | 'delete') {
  for (const query of client.getQueryCache().findAll({ queryKey: keyPrefix })) {
    const queryKey = query.queryKey
    client.setQueryData(queryKey, (old) => {
      const envelope = record(old)
      if (!envelope || !Array.isArray(envelope.items)) return old
      return { ...envelope, items: updateCalendarRangeList(envelope.items as Entity[], row, model, action, queryKey) }
    })
  }
}

function updateEntityList(
  items: Entity[],
  row: OutboxRow,
  model: Entity | null,
  action: 'upsert' | 'update' | 'delete',
): Entity[] {
  if (!row.entity_id) return items
  const index = items.findIndex((item) => item.id === row.entity_id)
  if (action === 'delete') return index < 0 ? items : items.filter((item) => item.id !== row.entity_id)
  if (!model) return items
  if (action === 'update' && index < 0) return items
  if (index < 0) return [...items, model]
  return items.map((item) => {
    if (item.id !== row.entity_id) return item
    const merged = { ...item, ...model }
    // Pending state is derived from live outbox metadata, never retained as a
    // server-confirmed domain field after reconciliation.
    delete merged.__outbox_state
    return merged
  })
}

function purgePrivateRowFromCache(client: QueryClient, keys: QueryKey[], row: OutboxRow) {
  const hiddenIds = new Set<string>()
  if (row.entity_id) hiddenIds.add(row.entity_id)
  const hiddenReminderSource = row.resource === 'reminder' ? row.parent_id : null
  if (row.parent_id && ['task_item', 'note_item', 'entry', 'subscription'].includes(row.resource)) {
    hiddenIds.add(row.parent_id)
  }
  if (hiddenIds.size === 0 && !hiddenReminderSource) return
  for (const key of keys) {
    client.setQueriesData({ queryKey: key }, (old) => {
      if (Array.isArray(old)) return old.filter((item) => {
        const entity = record(item)
        return !entity || (typeof entity.id !== 'string' || !hiddenIds.has(entity.id)) &&
          !(hiddenReminderSource && entity.source_id === hiddenReminderSource)
      })
      const envelope = record(old)
      if (!envelope || !Array.isArray(envelope.items)) return old
      return {
        ...envelope,
        items: envelope.items.filter((item) => {
          const entity = record(item)
          return !entity || (typeof entity.id !== 'string' || !hiddenIds.has(entity.id)) &&
            !(hiddenReminderSource && entity.source_id === hiddenReminderSource)
        }),
      }
    })
  }
}

function updateChildList(
  parent: Entity,
  row: OutboxRow,
  model: Entity | null,
  action: 'upsert' | 'update' | 'delete',
): Entity {
  const children = Array.isArray(parent.items) ? parent.items as Entity[] : []
  const next = updateEntityList(children, row, model, action)
    .sort((a, b) => Number(a.position ?? 0) - Number(b.position ?? 0))
  return { ...parent, items: next }
}

function mutateParents(client: QueryClient, key: QueryKey, row: OutboxRow, change: (parent: Entity) => Entity) {
  const parentId = row.parent_id
  if (!parentId) return
  const apply = (items: Entity[]) => items.map((item) => item.id === parentId ? change(item) : item)
  if (key[0] === 'notes') mutateNoteList(client, apply)
  else mutateEnvelope(client, key, apply)
}

function addIsoDays(day: string, amount: number): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return null
  const date = new Date(`${day}T00:00:00Z`)
  if (Number.isNaN(date.getTime())) return null
  date.setUTCDate(date.getUTCDate() + amount)
  return date.toISOString().slice(0, 10)
}

function calendarRangeIncludes(queryKey: QueryKey, from: string, to: string): boolean {
  if (queryKey[0] === 'calendar' && queryKey[1] === 'events') {
    if (typeof queryKey[2] === 'number' && typeof queryKey[3] === 'number') {
      const start = from.slice(0, 7)
      const end = to.slice(0, 7)
      const first = `${queryKey[2]}-${String(queryKey[3]).padStart(2, '0')}`
      const nextMonth = queryKey[3] === 12
        ? `${queryKey[2] + 1}-01`
        : `${queryKey[2]}-${String(queryKey[3] + 1).padStart(2, '0')}`
      return start < nextMonth && end >= first
    }
    if (typeof queryKey[2] === 'string') {
      const rangeEnd = addIsoDays(queryKey[2], 30)
      return rangeEnd !== null && from < rangeEnd && to >= queryKey[2]
    }
  }
  if (queryKey[0] === 'calendar' && queryKey[1] === 'annotations' &&
    typeof queryKey[2] === 'string' && typeof queryKey[3] === 'string') {
    return from <= queryKey[3] && to >= queryKey[2]
  }
  if (queryKey[0] === 'calendar' && queryKey[1] === 'tasks' &&
    typeof queryKey[3] === 'string' && typeof queryKey[4] === 'string') {
    return from <= queryKey[4] && to >= queryKey[3]
  }
  if (queryKey[0] === 'tasks' && queryKey[1] === 'timeline' &&
    typeof queryKey[3] === 'string' && typeof queryKey[4] === 'string') {
    const endExclusive = addIsoDays(queryKey[4], 1)
    return endExclusive !== null && from < endExclusive && to >= queryKey[3]
  }
  return true
}

function updateCalendarRangeList(
  items: Entity[],
  row: OutboxRow,
  model: Entity | null,
  action: 'upsert' | 'update' | 'delete',
  queryKey: QueryKey,
  pendingMarker = true,
): Entity[] {
  if (!row.entity_id) return items
  const current = items.find((item) => item.id === row.entity_id)
  if (action === 'delete') return current ? items.filter((item) => item.id !== row.entity_id) : items
  if (!model || (action === 'update' && !current)) return items
  const merged = current ? { ...current, ...model } : model
  let from: string | undefined
  let to: string | undefined
  if (row.operation_kind.startsWith('calendar_event.')) {
    const startsAt = merged.starts_at
    if (typeof startsAt !== 'string') return items
    from = startsAt.slice(0, 10)
    to = from
  } else if (row.operation_kind.startsWith('day_annotation.')) {
    if (typeof merged.starts_on !== 'string' || typeof merged.ends_on !== 'string') return items
    from = merged.starts_on
    to = merged.ends_on
  } else {
    const due = typeof merged.due_on === 'string'
      ? merged.due_on
      : typeof merged.due_at === 'string'
        ? merged.due_at.slice(0, 10)
        : null
    if (!due) return items.filter((item) => item.id !== row.entity_id)
    if (queryKey[2] === 'open' && merged.status === 'completed') {
      return items.filter((item) => item.id !== row.entity_id)
    }
    if (queryKey[0] === 'tasks' && queryKey[1] === 'timeline' &&
      queryKey[2] === 'completed' && merged.status !== 'completed') {
      return items.filter((item) => item.id !== row.entity_id)
    }
    from = due
    to = due
  }
  if (!from || !to || !calendarRangeIncludes(queryKey, from, to)) {
    return current ? items.filter((item) => item.id !== row.entity_id) : items
  }
  const next = { ...merged }
  if (pendingMarker) next.__outbox_state = 'pending'
  else delete next.__outbox_state
  return current
    ? items.map((item) => item.id === row.entity_id ? next : item)
    : action === 'upsert' ? [...items, next] : items
}

function applyTypedOverlay(client: QueryClient, row: OutboxRow) {
  const kind = row.operation_kind as OperationKind
  if (!(kind in definitions)) return
  const spec: AdapterSpec = definitions[kind]
  const keys = spec.keys({ path: row.path, body: row.body, entityId: row.entity_id, parentId: row.parent_id })
  const body = objectBody(row.body)
  const optimisticEntity = (row as OutboxRow & { optimistic_entity?: Json }).optimistic_entity
  const restoredModel = isRestoreOperation(kind) &&
    optimisticEntity && record(optimisticEntity)
    ? { ...(optimisticEntity as Entity), __outbox_state: 'pending' }
    : null
  const model = restoredModel ?? spec.optimisticDto({ path: row.path, body: row.body, entityId: row.entity_id, parentId: row.parent_id })
  const deleting = spec.method === 'DELETE'
  const action = deleting ? 'delete' :
    kind.endsWith('.create') || isRestoreOperation(kind) ? 'upsert' : 'update'

  // Keep reminder lists server-confirmed while a revision-checked command waits.
  // The public-cache sanitizer deliberately does not persist one-shot reminders.
  if (kind === 'reminder.save' || kind === 'reminder.cancel') return

  if (kind.startsWith('task_item.')) {
    for (const key of keys) mutateParents(client, key, row, (parent) => updateChildList(parent, row, model, action))
    return
  }
  if (kind.startsWith('note_item.')) {
    if (kind === 'note_item.reorder') {
      const positions = Array.isArray(body.items) ? body.items as Array<Record<string, unknown>> : []
      mutateNoteList(client, (parents) => parents.map((parent) => {
        if (parent.id !== row.parent_id || !Array.isArray(parent.items)) return parent
        return {
          ...parent,
          items: (parent.items as Entity[]).map((item) => {
            const position = positions.find((entry) => entry.id === item.id)?.position
            return typeof position === 'number' ? { ...item, position } : item
          }).sort((a, b) => Number(a.position ?? 0) - Number(b.position ?? 0)),
        }
      }))
    } else {
      mutateNoteList(client, (parents) => parents.map((parent) =>
        parent.id === row.parent_id ? updateChildList(parent, row, model, action) : parent,
      ))
    }
    return
  }
  if (kind.startsWith('task.')) {
    for (const key of keys) {
      if ((key[0] === 'calendar' && key[1] === 'tasks') || (key[0] === 'tasks' && key[1] === 'timeline')) {
        mutateCalendarRangeQueries(client, key, row, model, action)
      } else {
        mutateEnvelope(client, key, (items) => updateEntityList(items, row, model, action))
      }
    }
    return
  }
  if (kind.startsWith('note.')) {
    mutateNoteList(client, (items) => updateEntityList(items, row, model, action))
    return
  }
  for (const key of keys) {
    if (kind.startsWith('calendar_source.')) {
      mutateEnvelope(client, key, (items) => updateEntityList(items, row, model, action))
    } else if (kind.startsWith('calendar_event.') || kind.startsWith('day_annotation.')) {
      mutateCalendarRangeQueries(client, key, row, model, action)
    } else if (kind.startsWith('tracker_group.')) {
      mutateEnvelope(client, key, (items) => updateEntityList(items, row, model, action))
    } else if (kind.startsWith('tracker.') || kind.startsWith('entry.')) {
      // Dashboard totals and tracker projections are server-derived. Only their
      // source collections are overlaid; derived values wait for server success.
      mutateEnvelope(client, key, (items) => updateEntityList(items, row, model, action))
    } else if (kind.startsWith('subscription.')) {
      if (kind === 'subscription.renew') continue
      mutateEnvelope(client, key, (items) => updateEntityList(items, row, model, action))
    } else if (kind.startsWith('setting.')) {
      const modelKey = record(model)?.key
      mutateEnvelope(client, key, (items) => items.map((item) => item.key === modelKey ? { ...item, ...model } : item))
    }
  }
}

export function hasVerifiedPrivateSession(
  session: unknown,
  updatedAt: number,
  online: boolean,
  now = Date.now(),
): boolean {
  const value = record(session)
  const privateUntil = typeof value?.private_until === 'string'
    ? Date.parse(value.private_until)
    : Number.NaN
  return online && updatedAt > 0 && updatedAt <= now &&
    value?.offline_bootstrap !== true && Number.isFinite(privateUntil) && privateUntil > now
}

export function hasLivePrivateSession(client: QueryClient, now = Date.now()): boolean {
  const queryState = client.getQueryState(['session'])
  const session = client.getQueryData(['session'])
  const queryMeta = client.getQueryCache().find({ queryKey: ['session'], exact: true })?.meta
  const offlineBootstrap = record(queryMeta)?.offline_bootstrap === true
  return !offlineBootstrap && queryState?.status === 'success' &&
    !queryState.isInvalidated && queryState.fetchFailureCount === 0 &&
    hasVerifiedPrivateSession(
      session,
      queryState.dataUpdatedAt,
      typeof navigator !== 'undefined' && navigator.onLine === true,
      now,
    )
}

/** Reapply every stored public command and private commands only after a live unlock. */
export async function replayPendingOverlays(client: QueryClient): Promise<number> {
  const rows = await listOutbox()
  let applied = 0
  for (const row of rows) {
    let adapter: OutboxAdapter
    try {
      adapter = adapterFor(row.operation_kind)
    } catch {
      continue
    }
    const keys = adapter.affectedQueryKeys({
      path: row.path,
      body: row.body,
      entityId: row.entity_id,
      parentId: row.parent_id,
    })
    if (keys.length === 0) continue
    captureBaseline(client, keys, row)
    await Promise.all(keys.map((key) => client.cancelQueries({ queryKey: key })))
    if (requiresPrivateRow(row) && !hasLivePrivateSession(client)) {
      purgePrivateRowFromCache(client, keys, row)
      continue
    }
    applyTypedOverlay(client, row)
    applied += 1
  }
  return applied
}

function serverResult(kind: OperationKind, response: unknown): Entity | null {
  const value = record(response)
  if (!value) return null
  const model = kind === 'subscription.renew' ? record(value.subscription) : value
  if (!model || typeof model.id !== 'string') return null
  // Restore endpoints return only {id,status}; never replace a full domain
  // model with that acknowledgement.
  if ('status' in model && Object.keys(model).length <= 2) return null
  return model as Entity
}

function reconcileValue(kind: OperationKind, row: OutboxRow, value: unknown, response: unknown, queryKey: QueryKey): unknown {
  if (kind === 'note_item.reorder' && Array.isArray(response)) {
    const items = response as Entity[]
    return Array.isArray(value)
      ? (value as Entity[]).map((note) => note.id === row.parent_id ? { ...note, items } : note)
      : value
  }
  if (kind.startsWith('setting.')) {
    const serverSetting = record(response)
    if (!serverSetting) return value
    const key = kind === 'setting.show_list_price.update'
      ? 'show_list_price'
      : 'subscription_expiry_lead_days'
    const item = { ...serverSetting, key }
    const updateSettings = (items: Entity[]) => {
      const index = items.findIndex((setting) => setting.key === key)
      if (index < 0) return [...items, item]
      return items.map((setting) => setting.key === key ? item : setting)
    }
    if (Array.isArray(value)) return updateSettings(value as Entity[])
    const envelope = record(value)
    return envelope && Array.isArray(envelope.items)
      ? { ...envelope, items: updateSettings(envelope.items as Entity[]) }
      : value
  }
  const model = serverResult(kind, response)
  if (kind === 'reminder.save' && model) {
    const envelope = record(value)
    if (!envelope || !Array.isArray(envelope.items) || queryKey[1] !== 'active') return value
    const items = envelope.items as Entity[]
    const nextItems = items.filter((item) =>
      item.source_id !== model.source_id || item.source_kind !== model.source_kind,
    )
    if (['pending', 'sending', 'needs_reschedule'].includes(String(model.status))) nextItems.push(model)
    return { ...envelope, items: nextItems }
  }
  if (!model || !row.entity_id) return value
  if (kind.startsWith('task_item.')) {
    const action = kind === 'task_item.create' ? 'upsert' : 'update'
    const reconcileParent = (parent: Entity) => parent.id === row.parent_id
      ? { ...parent, items: updateEntityList(Array.isArray(parent.items) ? parent.items as Entity[] : [], row, model, action) }
      : parent
    if (Array.isArray(value)) return (value as Entity[]).map(reconcileParent)
    const envelope = record(value)
    return envelope && Array.isArray(envelope.items)
      ? { ...envelope, items: (envelope.items as Entity[]).map(reconcileParent) }
      : value
  }
  if (kind.startsWith('note_item.')) {
    return Array.isArray(value)
      ? (value as Entity[]).map((note) => note.id === row.parent_id
        ? { ...note, items: updateEntityList(Array.isArray(note.items) ? note.items as Entity[] : [], row, model, kind === 'note_item.create' ? 'upsert' : 'update') }
        : note)
      : value
  }
  const action = kind.endsWith('.create') ? 'upsert' : 'update'
  if (kind.startsWith('calendar_event.') || kind.startsWith('day_annotation.') ||
    (kind.startsWith('task.') && (queryKey[0] === 'calendar' || queryKey[1] === 'timeline'))) {
    const items = Array.isArray(value) ? value as Entity[] : record(value)?.items as Entity[] | undefined
    if (!items) return value
    const nextItems = updateCalendarRangeList(items, row, model, action, queryKey, false)
    return Array.isArray(value) ? nextItems : { ...record(value), items: nextItems }
  }
  if (Array.isArray(value)) return updateEntityList(value as Entity[], row, model, action)
  const envelope = record(value)
  if (envelope && Array.isArray(envelope.items)) {
    return { ...envelope, items: updateEntityList(envelope.items as Entity[], row, model, action) }
  }
  return value
}

async function rebuildFromConfirmedBaseline(client: QueryClient, keys: QueryKey[]) {
  restoreBaseline(client, keys)
  const remaining = await listOutbox()
  const scope = new Set(keys.map(keyId))
  // Private rows are deliberately never replayed here. The adapter contract
  // carries no live gate token, so a rebuild after TTL/lock must fail closed.
  for (const row of remaining) {
    if (requiresPrivateRow(row)) continue
    const kind = row.operation_kind as OperationKind
    if (!(kind in definitions)) continue
    const rowSpec: AdapterSpec = definitions[kind]
    const rowKeys = rowSpec.keys({ path: row.path, body: row.body, entityId: row.entity_id, parentId: row.parent_id })
    if (rowKeys.some((key) => scope.has(keyId(key)))) applyTypedOverlay(client, row)
  }
}

const routePatterns: Record<OperationKind, RegExp> = {
  'task.create': /^\/api\/tasks$/, 'task.update': /^\/api\/tasks\/[^/?]+$/, 'task.delete': /^\/api\/tasks\/[^/?]+$/, 'task.restore': /^\/api\/tasks\/[^/?]+\/restore$/,
  'task_item.create': /^\/api\/tasks\/[^/?]+\/items$/, 'task_item.update': /^\/api\/tasks\/[^/?]+\/items\/[^/?]+$/, 'task_item.delete': /^\/api\/tasks\/[^/?]+\/items\/[^/?]+$/,
  'note.create': /^\/api\/notes$/, 'note.update': /^\/api\/notes\/[^/?]+$/, 'note.delete': /^\/api\/notes\/[^/?]+$/, 'note.restore': /^\/api\/notes\/[^/?]+\/restore$/,
  'note_item.create': /^\/api\/notes\/[^/?]+\/items$/, 'note_item.update': /^\/api\/notes\/[^/?]+\/items\/[^/?]+$/, 'note_item.delete': /^\/api\/notes\/[^/?]+\/items\/[^/?]+$/, 'note_item.reorder': /^\/api\/notes\/[^/?]+\/items\/positions$/,
  'calendar_source.create': /^\/api\/calendar\/sources$/, 'calendar_source.update': /^\/api\/calendar\/sources\/[^/?]+$/, 'calendar_source.delete': /^\/api\/calendar\/sources\/[^/?]+$/, 'calendar.import': /^\/api\/calendar\/sources\/[^/?]+\/import$/,
  'calendar_event.create': /^\/api\/calendar\/events$/, 'calendar_event.update': /^\/api\/calendar\/events\/[^/?]+$/, 'calendar_event.delete': /^\/api\/calendar\/events\/[^/?]+$/,
  'day_annotation.create': /^\/api\/calendar\/annotations$/, 'day_annotation.update': /^\/api\/calendar\/annotations\/[^/?]+$/, 'day_annotation.delete': /^\/api\/calendar\/annotations\/[^/?]+$/,
  'tracker_group.create': /^\/api\/tracker\/groups$/, 'tracker_group.update': /^\/api\/tracker\/groups\/[^/?]+$/, 'tracker_group.delete': /^\/api\/tracker\/groups\/[^/?]+$/,
  'tracker.create': /^\/api\/tracker\/trackers$/, 'tracker.update': /^\/api\/tracker\/trackers\/[^/?]+$/, 'tracker.archive': /^\/api\/tracker\/trackers\/[^/?]+$/, 'tracker.restore': /^\/api\/tracker\/trackers\/[^/?]+\/restore$/,
  'entry.create': /^\/api\/tracker\/entries$/, 'entry.update': /^\/api\/tracker\/entries\/[^/?]+$/, 'entry.delete': /^\/api\/tracker\/entries\/[^/?]+$/, 'entry.restore': /^\/api\/tracker\/entries\/[^/?]+\/restore$/,
  'subscription.create': /^\/api\/subscriptions$/, 'subscription.update': /^\/api\/subscriptions\/[^/?]+$/, 'subscription.cancel': /^\/api\/subscriptions\/[^/?]+\/cancel$/, 'subscription.uncancel': /^\/api\/subscriptions\/[^/?]+\/uncancel$/, 'subscription.renew': /^\/api\/subscriptions\/[^/?]+\/renew$/, 'subscription.delete': /^\/api\/subscriptions\/[^/?]+$/, 'subscription.restore': /^\/api\/subscriptions\/[^/?]+\/restore$/,
  'setting.show_list_price.update': /^\/api\/settings\/show_list_price$/, 'setting.subscription_expiry_lead_days.update': /^\/api\/settings\/subscription_expiry_lead_days$/, 'reminder.confirm': /^\/api\/reminder-dispatch\/[^/?]+\/confirm$/,
  'reminder.save': /^\/api\/reminders\/(task|event|tracker)\/[^/?]+$/, 'reminder.cancel': /^\/api\/reminders\/[^/?]+\?revision=[1-9][0-9]*$/,
}

function validUuidV7(value: unknown): value is string {
  return typeof value === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
}

function validExistingUuid(value: unknown): value is string {
  return typeof value === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
}

function routeEntityId(kind: OperationKind, path: string): string | null {
  const patterns: Partial<Record<OperationKind, RegExp>> = {
    'task.update': /^\/api\/tasks\/([^/]+)$/,
    'task.delete': /^\/api\/tasks\/([^/]+)$/,
    'task.restore': /^\/api\/tasks\/([^/]+)\/restore$/,
    'task_item.update': /^\/api\/tasks\/[^/]+\/items\/([^/]+)$/,
    'task_item.delete': /^\/api\/tasks\/[^/]+\/items\/([^/]+)$/,
    'note.update': /^\/api\/notes\/([^/]+)$/,
    'note.delete': /^\/api\/notes\/([^/]+)$/,
    'note.restore': /^\/api\/notes\/([^/]+)\/restore$/,
    'note_item.update': /^\/api\/notes\/[^/]+\/items\/([^/]+)$/,
    'note_item.delete': /^\/api\/notes\/[^/]+\/items\/([^/]+)$/,
    'calendar_source.update': /^\/api\/calendar\/sources\/([^/]+)$/,
    'calendar_source.delete': /^\/api\/calendar\/sources\/([^/]+)$/,
    'calendar.import': /^\/api\/calendar\/sources\/([^/]+)\/import$/,
    'calendar_event.update': /^\/api\/calendar\/events\/([^/]+)$/,
    'calendar_event.delete': /^\/api\/calendar\/events\/([^/]+)$/,
    'day_annotation.update': /^\/api\/calendar\/annotations\/([^/]+)$/,
    'day_annotation.delete': /^\/api\/calendar\/annotations\/([^/]+)$/,
    'tracker_group.update': /^\/api\/tracker\/groups\/([^/]+)$/,
    'tracker_group.delete': /^\/api\/tracker\/groups\/([^/]+)$/,
    'tracker.update': /^\/api\/tracker\/trackers\/([^/]+)$/,
    'tracker.archive': /^\/api\/tracker\/trackers\/([^/]+)$/,
    'tracker.restore': /^\/api\/tracker\/trackers\/([^/]+)\/restore$/,
    'entry.update': /^\/api\/tracker\/entries\/([^/]+)$/,
    'entry.delete': /^\/api\/tracker\/entries\/([^/]+)$/,
    'entry.restore': /^\/api\/tracker\/entries\/([^/]+)\/restore$/,
    'subscription.update': /^\/api\/subscriptions\/([^/]+)$/,
    'subscription.cancel': /^\/api\/subscriptions\/([^/]+)\/cancel$/,
    'subscription.uncancel': /^\/api\/subscriptions\/([^/]+)\/uncancel$/,
    'subscription.renew': /^\/api\/subscriptions\/([^/]+)\/renew$/,
    'subscription.delete': /^\/api\/subscriptions\/([^/]+)$/,
    'subscription.restore': /^\/api\/subscriptions\/([^/]+)\/restore$/,
    'reminder.cancel': /^\/api\/reminders\/([^/?]+)\?revision=[1-9][0-9]*$/,
  }
  return path.match(patterns[kind] ?? /(?!)$/)?.[1] ?? null
}

function routeParentId(kind: OperationKind, path: string): string | null {
  const patterns: Partial<Record<OperationKind, RegExp>> = {
    'task_item.create': /^\/api\/tasks\/([^/]+)\/items$/,
    'task_item.update': /^\/api\/tasks\/([^/]+)\/items\/[^/]+$/,
    'task_item.delete': /^\/api\/tasks\/([^/]+)\/items\/[^/]+$/,
    'note_item.create': /^\/api\/notes\/([^/]+)\/items$/,
    'note_item.update': /^\/api\/notes\/([^/]+)\/items\/[^/]+$/,
    'note_item.delete': /^\/api\/notes\/([^/]+)\/items\/[^/]+$/,
    'note_item.reorder': /^\/api\/notes\/([^/]+)\/items\/positions$/,
    'calendar.import': /^\/api\/calendar\/sources\/([^/]+)\/import$/,
    'reminder.save': /^\/api\/reminders\/(?:task|event|tracker)\/([^/?]+)$/,
  }
  return path.match(patterns[kind] ?? /(?!)$/)?.[1] ?? null
}

export type OperationKind = keyof typeof definitions

function adapterForSpec<K extends OperationKind>(operationKind: K): OutboxAdapter {
  const spec: AdapterSpec = definitions[operationKind]
  return {
    method: spec.method,
    resource: spec.resource,
    idempotencyMode: spec.idempotencyMode,
    affectedQueryKeys: (input) => spec.keys(input),
    encodeCommand(input) {
      if (input.operationKind !== operationKind) {
        throw new Error(`Outbox adapter mismatch: ${input.operationKind}`)
      }
      const path = spec.route(input)
      if (!routePatterns[operationKind].test(path)) {
        throw new Error(`Invalid route for ${operationKind}`)
      }
      const body = input.body ?? null
      const id = idFrom(input)
      const parentId = input.parentId ?? null
      const bodyId = objectBody(body).id
      if (spec.idempotencyMode === 'client_uuid' &&
        (!validUuidV7(bodyId) || id !== bodyId)) {
        throw new Error(`A stable body.id UUIDv7 is required for ${operationKind}`)
      }
      if (id !== null && spec.resource !== 'setting' && !validExistingUuid(id)) {
        throw new Error(`Invalid entity UUID for ${operationKind}`)
      }
      const pathEntityId = routeEntityId(operationKind, path)
      if (pathEntityId && id?.toLowerCase() !== pathEntityId.toLowerCase()) {
        throw new Error(`Entity ID does not match route for ${operationKind}`)
      }
      const pathParentId = routeParentId(operationKind, path)
      if (pathParentId && (!parentId || parentId.toLowerCase() !== pathParentId.toLowerCase())) {
        throw new Error(`Parent ID does not match route for ${operationKind}`)
      }
      const bodyParentId = ({
        'calendar_event.create': objectBody(body).source_id,
        'tracker.create': objectBody(body).group_id,
        'entry.create': objectBody(body).tracker_id,
        'subscription.create': objectBody(body).tracker_id,
      } as Partial<Record<OperationKind, Json | undefined>>)[operationKind]
      if (bodyParentId && (!parentId || bodyParentId !== parentId)) {
        throw new Error(`Parent ID does not match body for ${operationKind}`)
      }
      if ((operationKind.startsWith('entry.') || operationKind.startsWith('subscription.') ||
        operationKind.startsWith('tracker.') || operationKind === 'reminder.save' ||
        operationKind === 'reminder.cancel') && input.requiresPrivate === undefined) {
        throw new Error(`Privacy gate state is required for ${operationKind}`)
      }
      if (parentId !== null && !validExistingUuid(parentId)) throw new Error(`Invalid parent UUID for ${operationKind}`)
      return {
        operation_kind: operationKind,
        resource: spec.resource,
        method: spec.method,
        path,
        body,
        ...(input.optimisticEntity === undefined ? {} : { optimistic_entity: input.optimisticEntity }),
        entity_id: id,
        parent_id: parentId,
        // A body that makes an entity private can never downgrade the command's
        // gate classification supplied from its existing entity metadata.
        requires_private: input.requiresPrivate === true || objectBody(body).is_private === true,
        idempotency_mode: spec.idempotencyMode,
        dependency_operation_id: input.dependencyOperationId ?? null,
        group_id: input.groupId ?? null,
        affected_query_keys: spec.keys(input),
      }
    },
    async optimisticApply(client, row) {
      const keys = spec.keys({ path: row.path, body: row.body, entityId: row.entity_id, parentId: row.parent_id })
      captureBaseline(client, keys, row)
      await Promise.all(keys.map((key) => client.cancelQueries({ queryKey: key })))
      // Lock/TTL purge may run while cancelQueries is awaiting. Re-read the live
      // session after that await; cached/bootstrap permission is insufficient.
      if (requiresPrivateRow(row) && !hasLivePrivateSession(client)) {
        purgePrivateRowFromCache(client, keys, row)
        return
      }
      applyTypedOverlay(client, row)
    },
    async reconcileSuccess(client, row, response) {
      if (spec.method === 'DELETE' || kindIsSideEffect(operationKind) || response == null) return
      const keys = spec.keys({ path: row.path, body: row.body, entityId: row.entity_id, parentId: row.parent_id })
      if (isRestoreOperation(operationKind) && record(response)?.status === 'restored') {
        if (requiresPrivateRow(row) && !hasLivePrivateSession(client)) {
          purgePrivateRowFromCache(client, keys, row)
          return
        }
        const restored = record((row as OutboxRow & { optimistic_entity?: Json }).optimistic_entity)
        if (!restored) return
        const confirmed = { ...restored }
        delete confirmed.__outbox_state
        if (!requiresPrivateRow(row)) {
          captureBaseline(client, keys, row)
          const byKey = confirmedBaselines.get(client)
          for (const key of keys) {
            const id = keyId(key)
            const snapshot = byKey?.get(id)
            if (!snapshot) continue
            byKey?.set(id, snapshot.map(([queryKey, value]) => {
              if (operationKind === 'task.restore' &&
                ((queryKey[0] === 'calendar' && queryKey[1] === 'tasks') ||
                  (queryKey[0] === 'tasks' && queryKey[1] === 'timeline'))) {
                const envelope = record(value)
                return [queryKey, envelope && Array.isArray(envelope.items)
                  ? { ...envelope, items: updateCalendarRangeList(envelope.items as Entity[], row, confirmed, 'upsert', queryKey, false) }
                  : value]
              }
              if (Array.isArray(value)) return [queryKey, updateEntityList(value as Entity[], row, confirmed, 'upsert')]
              const envelope = record(value)
              return [queryKey, envelope && Array.isArray(envelope.items)
                ? { ...envelope, items: updateEntityList(envelope.items as Entity[], row, confirmed, 'upsert') }
                : value]
            }))
          }
        }
        for (const key of keys) {
          client.setQueriesData({ queryKey: key }, (value) => {
            if (operationKind === 'task.restore' &&
              ((key[0] === 'calendar' && key[1] === 'tasks') || (key[0] === 'tasks' && key[1] === 'timeline'))) {
              const envelope = record(value)
              return envelope && Array.isArray(envelope.items)
                ? { ...envelope, items: updateCalendarRangeList(envelope.items as Entity[], row, confirmed, 'upsert', key, false) }
                : value
            }
            if (Array.isArray(value)) return updateEntityList(value as Entity[], row, confirmed, 'upsert')
            const envelope = record(value)
            return envelope && Array.isArray(envelope.items)
              ? { ...envelope, items: updateEntityList(envelope.items as Entity[], row, confirmed, 'upsert') }
              : value
          })
        }
        return
      }
      if (operationKind === 'reminder.save') {
        if (requiresPrivateRow(row) && !hasLivePrivateSession(client)) {
          purgePrivateRowFromCache(client, keys, row)
          return
        }
        for (const query of client.getQueryCache().findAll({ queryKey: keys[0] })) {
          const queryKey = query.queryKey
          client.setQueryData(queryKey, (value) =>
            reconcileValue(operationKind, row, value, response, queryKey),
          )
        }
        return
      }
      if (requiresPrivateRow(row)) {
        // Never put a private server acknowledgement into the rollback WeakMap.
        // Reconcile directly into live query state only while the verified gate
        // still holds; otherwise erase the entity and leave the public baseline.
        if (!hasLivePrivateSession(client)) {
          purgePrivateRowFromCache(client, keys, row)
          return
        }
        for (const query of client.getQueryCache().findAll({ queryKey: keys[0] })) {
          const queryKey = query.queryKey
          client.setQueryData(queryKey, (value) => {
            if (Array.isArray(value)) return reconcileValue(operationKind, row, value, response, queryKey)
            const envelope = record(value)
            if (envelope && Array.isArray(envelope.items)) {
              return reconcileValue(operationKind, row, value, response, queryKey)
            }
            return value
          })
        }
        return
      }
      captureBaseline(client, keys, row)
      const byKey = confirmedBaselines.get(client)
      for (const key of keys) {
        const id = keyId(key)
        const snapshot = byKey?.get(id)
        if (!snapshot) continue
        byKey?.set(id, snapshot.map(([queryKey, value]) => [
          queryKey,
          reconcileValue(operationKind, row, value, response, queryKey),
        ]))
      }
      await rebuildFromConfirmedBaseline(client, keys)
    },
    async discardOrRollback(client, row) {
      const keys = spec.keys({ path: row.path, body: row.body, entityId: row.entity_id, parentId: row.parent_id })
      await rebuildFromConfirmedBaseline(client, keys)
    },
    optimisticResponse(row) {
      return spec.optimisticDto({
        path: row.path,
        body: row.body,
        entityId: row.entity_id,
        parentId: row.parent_id,
      })
    },
  }
}

function kindIsSideEffect(kind: OperationKind) {
  return kind === 'calendar.import' || kind === 'subscription.renew' || kind === 'reminder.confirm'
}

export const outboxAdapters = Object.fromEntries(
  (Object.keys(definitions) as OperationKind[]).map((kind) => [kind, adapterForSpec(kind)]),
) as Record<OperationKind, OutboxAdapter>

export function adapterFor(kind: string): OutboxAdapter {
  const adapter = outboxAdapters[kind as OperationKind]
  if (!adapter) throw new Error(`Unknown outbox operation: ${kind}`)
  return adapter
}

/** Requeue the original, atomically cancelled command tree and project every row. */
export async function restoreCancelledDomainTree(
  client: QueryClient,
  rows: OutboxRow[],
): Promise<OutboxRow[]> {
  const restored = await restoreCancelledOutbox(rows)
  for (const row of restored) await adapterFor(row.operation_kind).optimisticApply(client, row)
  window.dispatchEvent(new Event('microsched:outbox-flush-requested'))
  return restored
}
