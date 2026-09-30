import type { QueryClient, QueryKey } from '@tanstack/react-query'

import { listOutbox, type Json, type OutboxRow } from '@/lib/outbox-db'

export type CommandInput = {
  path: string
  body?: Json | null
  entityId?: string | null
  parentId?: string | null
  requiresPrivate?: boolean
  dependencyOperationId?: number | null
  groupId?: string | null
}

/**
 * Domain-owned command metadata. The queue core adds runtime fields (timestamps,
 * state and payload receipt) after this value is produced.
 */
export type EncodedCommand = {
  operation_kind: OperationKind
  resource: string
  method: OutboxRow['method']
  path: string
  body: Json | null
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
  method: OutboxRow['method']
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
  method: OutboxRow['method']
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
} as const satisfies Record<string, AdapterSpec>

type CacheSnapshot = Array<[QueryKey, unknown]>
const confirmedBaselines = new WeakMap<QueryClient, Map<string, CacheSnapshot>>()
const keyId = (key: QueryKey) => JSON.stringify(key)
const record = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null

function captureBaseline(client: QueryClient, keys: QueryKey[]) {
  let byKey = confirmedBaselines.get(client)
  if (!byKey) {
    byKey = new Map()
    confirmedBaselines.set(client, byKey)
  }
  for (const key of keys) {
    const id = keyId(key)
    if (!byKey.has(id)) byKey.set(id, client.getQueriesData({ queryKey: key }))
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

function updateEntityList(
  items: Entity[],
  row: OutboxRow,
  model: Entity | null,
  action: 'upsert' | 'delete',
): Entity[] {
  if (!row.entity_id) return items
  const index = items.findIndex((item) => item.id === row.entity_id)
  if (action === 'delete') return index < 0 ? items : items.filter((item) => item.id !== row.entity_id)
  if (!model) return items
  if (index < 0) return [...items, model]
  return items.map((item) => item.id === row.entity_id ? { ...item, ...model } : item)
}

function updateChildList(
  parent: Entity,
  row: OutboxRow,
  model: Entity | null,
  action: 'upsert' | 'delete',
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

function listKeyFits(operationKind: OperationKind, queryKey: QueryKey, row: OutboxRow): boolean {
  if (operationKind === 'calendar_event.create' || operationKind === 'calendar_event.update') {
    const startsAt = objectBody(row.body).starts_at
    if (typeof startsAt !== 'string') return false
    const day = startsAt.slice(0, 10)
    if (typeof queryKey[2] === 'number') {
      return queryKey[2] === Number(day.slice(0, 4)) && queryKey[3] === Number(day.slice(5, 7))
    }
    // CalendarScreen stores one requested range start; exact-day matching avoids
    // painting a new event into an unrelated range whose bounds are not in its key.
    return queryKey[2] === day
  }
  if (operationKind === 'day_annotation.create' || operationKind === 'day_annotation.update') {
    const body = objectBody(row.body)
    const from = body.starts_on
    const to = body.ends_on
    return typeof from === 'string' && typeof to === 'string' &&
      typeof queryKey[2] === 'string' && typeof queryKey[3] === 'string' &&
      from <= queryKey[3] && to >= queryKey[2]
  }
  return true
}

function applyTypedOverlay(client: QueryClient, row: OutboxRow) {
  const kind = row.operation_kind as OperationKind
  if (!(kind in definitions)) return
  const spec: AdapterSpec = definitions[kind]
  const keys = spec.keys({ path: row.path, body: row.body, entityId: row.entity_id, parentId: row.parent_id })
  const body = objectBody(row.body)
  const model = spec.optimisticDto({ path: row.path, body: row.body, entityId: row.entity_id, parentId: row.parent_id })
  const deleting = spec.method === 'DELETE'

  if (kind.startsWith('task_item.')) {
    for (const key of keys) mutateParents(client, key, row, (parent) => updateChildList(parent, row, model, deleting ? 'delete' : 'upsert'))
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
        parent.id === row.parent_id ? updateChildList(parent, row, model, deleting ? 'delete' : 'upsert') : parent,
      ))
    }
    return
  }
  if (kind.startsWith('task.')) {
    for (const key of keys) mutateEnvelope(client, key, (items) => updateEntityList(items, row, model, deleting ? 'delete' : 'upsert'))
    return
  }
  if (kind.startsWith('note.')) {
    mutateNoteList(client, (items) => updateEntityList(items, row, model, deleting ? 'delete' : 'upsert'))
    return
  }
  for (const key of keys) {
    if (!listKeyFits(kind, key, row)) continue
    if (kind.startsWith('calendar_source.')) {
      mutateEnvelope(client, key, (items) => updateEntityList(items, row, model, deleting ? 'delete' : 'upsert'))
    } else if (kind.startsWith('calendar_event.') || kind.startsWith('day_annotation.')) {
      mutateEnvelope(client, key, (items) => updateEntityList(items, row, model, deleting ? 'delete' : 'upsert'))
    } else if (kind.startsWith('tracker_group.')) {
      mutateEnvelope(client, key, (items) => updateEntityList(items, row, model, deleting ? 'delete' : 'upsert'))
    } else if (kind.startsWith('tracker.') || kind.startsWith('entry.')) {
      // Dashboard totals and tracker projections are server-derived. Only their
      // source collections are overlaid; derived values wait for server success.
      mutateEnvelope(client, key, (items) => updateEntityList(items, row, model, deleting ? 'delete' : 'upsert'))
    } else if (kind.startsWith('subscription.')) {
      if (kind === 'subscription.renew') continue
      mutateEnvelope(client, key, (items) => updateEntityList(items, row, model, deleting ? 'delete' : 'upsert'))
    } else if (kind.startsWith('setting.')) {
      mutateEnvelope(client, key, (items) => items.map((item) => item.key === model?.key ? { ...item, ...model } : item))
    }
  }
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

function reconcileValue(kind: OperationKind, row: OutboxRow, value: unknown, response: unknown): unknown {
  if (kind === 'note_item.reorder' && Array.isArray(response)) {
    const items = response as Entity[]
    return Array.isArray(value)
      ? (value as Entity[]).map((note) => note.id === row.parent_id ? { ...note, items } : note)
      : value
  }
  const model = serverResult(kind, response)
  if (!model || !row.entity_id) return value
  if (kind.startsWith('note_item.')) {
    return Array.isArray(value)
      ? (value as Entity[]).map((note) => note.id === row.parent_id
        ? { ...note, items: updateEntityList(Array.isArray(note.items) ? note.items as Entity[] : [], row, model, 'upsert') }
        : note)
      : value
  }
  if (Array.isArray(value)) return updateEntityList(value as Entity[], row, model, 'upsert')
  const envelope = record(value)
  if (envelope && Array.isArray(envelope.items)) {
    return { ...envelope, items: updateEntityList(envelope.items as Entity[], row, model, 'upsert') }
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
    if (row.requires_private) continue
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
}

function validUuidV7(value: unknown): value is string {
  return typeof value === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
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
      if (id !== null && spec.resource !== 'setting' && !validUuidV7(id)) {
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
        operationKind.startsWith('tracker.')) && input.requiresPrivate === undefined) {
        throw new Error(`Privacy gate state is required for ${operationKind}`)
      }
      if (parentId !== null && !validUuidV7(parentId)) throw new Error(`Invalid parent UUID for ${operationKind}`)
      return {
        operation_kind: operationKind,
        resource: spec.resource,
        method: spec.method,
        path,
        body,
        entity_id: id,
        parent_id: parentId,
        requires_private: input.requiresPrivate ?? objectBody(body).is_private === true,
        idempotency_mode: spec.idempotencyMode,
        dependency_operation_id: input.dependencyOperationId ?? null,
        group_id: input.groupId ?? null,
        affected_query_keys: spec.keys(input),
      }
    },
    async optimisticApply(client, row) {
      const keys = spec.keys({ path: row.path, body: row.body, entityId: row.entity_id, parentId: row.parent_id })
      captureBaseline(client, keys)
      await Promise.all(keys.map((key) => client.cancelQueries({ queryKey: key })))
      applyTypedOverlay(client, row)
    },
    async reconcileSuccess(client, row, response) {
      if (spec.method === 'DELETE' || kindIsSideEffect(operationKind) || response == null) return
      const keys = spec.keys({ path: row.path, body: row.body, entityId: row.entity_id, parentId: row.parent_id })
      captureBaseline(client, keys)
      const byKey = confirmedBaselines.get(client)
      for (const key of keys) {
        const id = keyId(key)
        const snapshot = byKey?.get(id)
        if (!snapshot) continue
        byKey?.set(id, snapshot.map(([queryKey, value]) => [
          queryKey,
          reconcileValue(operationKind, row, value, response),
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
