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
const noDto: AdapterSpec['optimisticDto'] = () => null
const taskKeys = () => [['tasks'], ['calendar']] as QueryKey[]
const noteKeys = () => [['notes']] as QueryKey[]
const calendarKeys = () => [['calendar']] as QueryKey[]
const trackerKeys = () => [['tracker']] as QueryKey[]
const subscriptionKeys = () => [['subscription'], ['tracker']] as QueryKey[]
const trackerAndSubsKeys = () => [['tracker'], ['subscription']] as QueryKey[]

/**
 * Each operation declares its route family, DTO defaults and query surface.
 * The DTOs intentionally contain the server's required defaults so queued creates
 * render like domain objects while retaining an explicit pending marker.
 */
const definitions = {
  'task.create': { method:'POST', resource:'task', idempotencyMode:'client_uuid', route:()=>'/api/tasks', keys:taskKeys, optimisticDto:(i:CommandInput)=>dto(i,{status:'open',items:[],pinned:false,is_private:false}) },
  'task.update': { method:'PATCH', resource:'task', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:taskKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'task.delete': { method:'DELETE', resource:'task', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:taskKeys, optimisticDto:noDto },
  'task.restore': { method:'POST', resource:'task', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:taskKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'task_item.create': { method:'POST', resource:'task_item', idempotencyMode:'client_uuid', route:(i:CommandInput)=>i.path, keys:taskKeys, optimisticDto:(i:CommandInput)=>dto(i,{is_completed:false}) },
  'task_item.update': { method:'PATCH', resource:'task_item', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:taskKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'task_item.delete': { method:'DELETE', resource:'task_item', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:taskKeys, optimisticDto:noDto },
  'note.create': { method:'POST', resource:'note', idempotencyMode:'client_uuid', route:()=>'/api/notes', keys:noteKeys, optimisticDto:(i:CommandInput)=>dto(i,{items:[],is_private:false,pinned:false}) },
  'note.update': { method:'PATCH', resource:'note', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:noteKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'note.delete': { method:'DELETE', resource:'note', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:noteKeys, optimisticDto:noDto },
  'note.restore': { method:'POST', resource:'note', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:noteKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'note_item.create': { method:'POST', resource:'note_item', idempotencyMode:'client_uuid', route:(i:CommandInput)=>i.path, keys:noteKeys, optimisticDto:(i:CommandInput)=>dto(i,{is_completed:false}) },
  'note_item.update': { method:'PATCH', resource:'note_item', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:noteKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'note_item.delete': { method:'DELETE', resource:'note_item', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:noteKeys, optimisticDto:noDto },
  'note_item.reorder': { method:'PATCH', resource:'note_item', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:noteKeys, optimisticDto:noDto },
  'calendar_source.create': { method:'POST', resource:'calendar_source', idempotencyMode:'client_uuid', route:()=>'/api/calendar/sources', keys:calendarKeys, optimisticDto:(i:CommandInput)=>dto(i,{events:[],is_private:false}) },
  'calendar_source.update': { method:'PATCH', resource:'calendar_source', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:calendarKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'calendar_source.delete': { method:'DELETE', resource:'calendar_source', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:calendarKeys, optimisticDto:noDto },
  'calendar.import': { method:'POST', resource:'calendar_source', idempotencyMode:'side_effect', route:(i:CommandInput)=>i.path, keys:calendarKeys, optimisticDto:noDto },
  'calendar_event.create': { method:'POST', resource:'calendar_event', idempotencyMode:'client_uuid', route:()=>'/api/calendar/events', keys:calendarKeys, optimisticDto:(i:CommandInput)=>dto(i,{is_private:false}) },
  'calendar_event.update': { method:'PATCH', resource:'calendar_event', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:calendarKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'calendar_event.delete': { method:'DELETE', resource:'calendar_event', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:calendarKeys, optimisticDto:noDto },
  'day_annotation.create': { method:'POST', resource:'day_annotation', idempotencyMode:'client_uuid', route:()=>'/api/calendar/annotations', keys:calendarKeys, optimisticDto:(i:CommandInput)=>dto(i,{is_private:false}) },
  'day_annotation.update': { method:'PATCH', resource:'day_annotation', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:calendarKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'day_annotation.delete': { method:'DELETE', resource:'day_annotation', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:calendarKeys, optimisticDto:noDto },
  'tracker_group.create': { method:'POST', resource:'tracker_group', idempotencyMode:'client_uuid', route:()=>'/api/tracker/groups', keys:trackerKeys, optimisticDto:(i:CommandInput)=>dto(i,{trackers:[],is_private:false}) },
  'tracker_group.update': { method:'PATCH', resource:'tracker_group', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:trackerKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'tracker_group.delete': { method:'DELETE', resource:'tracker_group', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:trackerKeys, optimisticDto:noDto },
  'tracker.create': { method:'POST', resource:'tracker', idempotencyMode:'client_uuid', route:()=>'/api/tracker/trackers', keys:trackerAndSubsKeys, optimisticDto:(i:CommandInput)=>dto(i,{last_entry_at:null,entry_count_30d:0,is_private:false}) },
  'tracker.update': { method:'PATCH', resource:'tracker', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:trackerAndSubsKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'tracker.archive': { method:'DELETE', resource:'tracker', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:trackerAndSubsKeys, optimisticDto:noDto },
  'tracker.restore': { method:'POST', resource:'tracker', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:trackerAndSubsKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'entry.create': { method:'POST', resource:'entry', idempotencyMode:'client_uuid', route:()=>'/api/tracker/entries', keys:trackerKeys, optimisticDto:(i:CommandInput)=>dto(i,{is_private:false}) },
  'entry.update': { method:'PATCH', resource:'entry', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:trackerKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'entry.delete': { method:'DELETE', resource:'entry', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:trackerKeys, optimisticDto:noDto },
  'entry.restore': { method:'POST', resource:'entry', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:trackerKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'subscription.create': { method:'POST', resource:'subscription', idempotencyMode:'client_uuid', route:()=>'/api/subscriptions', keys:subscriptionKeys, optimisticDto:(i:CommandInput)=>dto(i,{is_private:false}) },
  'subscription.update': { method:'PATCH', resource:'subscription', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:subscriptionKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'subscription.cancel': { method:'POST', resource:'subscription', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:subscriptionKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'subscription.uncancel': { method:'POST', resource:'subscription', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:subscriptionKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'subscription.renew': { method:'POST', resource:'subscription', idempotencyMode:'side_effect', route:(i:CommandInput)=>i.path, keys:subscriptionKeys, optimisticDto:noDto },
  'subscription.delete': { method:'DELETE', resource:'subscription', idempotencyMode:'postcondition', route:(i:CommandInput)=>i.path, keys:subscriptionKeys, optimisticDto:noDto },
  'subscription.restore': { method:'POST', resource:'subscription', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:subscriptionKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'setting.show_list_price.update': { method:'PATCH', resource:'setting', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:subscriptionKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  'setting.subscription_expiry_lead_days.update': { method:'PATCH', resource:'setting', idempotencyMode:'absolute', route:(i:CommandInput)=>i.path, keys:subscriptionKeys, optimisticDto:(i:CommandInput)=>dto(i) },
  // This is the existing scheduled tracker-reminder action, not Mimi's
  // confirmation surface. Its entry_id is created at the screen before enqueue.
  'reminder.confirm': { method:'POST', resource:'reminder', idempotencyMode:'side_effect', route:(i:CommandInput)=>i.path, keys:trackerKeys, optimisticDto:noDto },
} as const satisfies Record<string, AdapterSpec>

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
    // Domain cache reconciliation is intentionally deferred to the integration
    // coordinator. It owns the single post-flush invalidation after the final row.
    async optimisticApply() {},
    async reconcileSuccess(client, row, response) {
      if (row.entity_id && response && typeof response === 'object') {
        const model = response as Entity
        const queryKey = spec.keys({ path: row.path, body: row.body, entityId: row.entity_id })[0]
        if (queryKey?.[0] === 'tasks' || queryKey?.[0] === 'notes' || queryKey?.[0] === 'calendar') {
          const entity = spec.optimisticDto({ path: row.path, body: row.body, entityId: row.entity_id })
          if (entity) client.setQueriesData({ queryKey }, (old) => {
            if (!old || typeof old !== 'object' || !('items' in old) || !Array.isArray(old.items)) return old
            const items = old.items as Entity[]
            return { ...old, items: items.map((item) => item.id === row.entity_id ? model : item) }
          })
        }
      }
    },
    async discardOrRollback() {},
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

export const outboxAdapters = Object.fromEntries(
  (Object.keys(definitions) as OperationKind[]).map((kind) => [kind, adapterForSpec(kind)]),
) as Record<OperationKind, OutboxAdapter>

export function adapterFor(kind: string): OutboxAdapter {
  const adapter = outboxAdapters[kind as OperationKind]
  if (!adapter) throw new Error(`Unknown outbox operation: ${kind}`)
  return adapter
}
