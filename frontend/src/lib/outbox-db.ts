import Dexie, { type EntityTable } from 'dexie'

export type Json = null | boolean | number | string | Json[] | { [key: string]: Json }
export type OutboxState = 'pending' | 'auth_hold' | 'private_hold' | 'outcome_unknown' | 'failed' | 'suppressed'

export type OutboxRow = {
  operation_id?: number
  operation_kind: string
  resource: string
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  path: string
  body: Json | null
  payload_json: string
  payload_sha256: string
  payload_byte_length: number
  entity_id: string | null
  parent_id: string | null
  requires_private: boolean
  idempotency_mode: 'client_uuid' | 'absolute' | 'postcondition' | 'side_effect'
  dependency_operation_id: number | null
  group_id: string | null
  affected_query_keys: Json[][]
  state: OutboxState
  attempts: number
  next_attempt_at: number | null
  created_at: number
  last_error_code: string | null
  timeout_ms?: number
  optimistic_entity?: Json
}

export type EnqueueResult = OutboxRow & { cancelled_rows?: OutboxRow[] }

type OutboxDb = Dexie & { outbox: EntityTable<OutboxRow, 'operation_id'> }
let database: OutboxDb | null = null
let unavailable = false
const cancelledReceipts = new WeakMap<OutboxRow[], OutboxRow[]>()

function emitChanged() {
  window.dispatchEvent(new Event('microsched:outbox-changed'))
  try { const channel = new BroadcastChannel('microsched-outbox-events'); channel.postMessage('changed'); channel.close() } catch { /* Existing Dexie observation remains available. */ }
}

export async function outboxDatabase(): Promise<OutboxDb | null> {
  if (unavailable) return null
  if (database) return database
  try {
    const db = new Dexie('microsched-outbox') as OutboxDb
    db.version(1).stores({
      outbox: '++operation_id,state,next_attempt_at,dependency_operation_id,entity_id,group_id',
    })
    await db.open()
    database = db
    return db
  } catch {
    unavailable = true
    window.dispatchEvent(new Event('microsched:offline-unavailable'))
    return null
  }
}

function canonical(value: Json): string {
  if (typeof value === 'string' && /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(value)) throw new TypeError('Outbox payload must contain valid Unicode')
  if (value === null || typeof value === 'boolean' || typeof value === 'string') {
    return JSON.stringify(value)
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new TypeError('Outbox payload must contain finite numbers')
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) return `[${Array.from(value, canonical).join(',')}]`
  if (Object.getPrototypeOf(value) !== Object.prototype) {
    throw new TypeError('Outbox payload must contain plain JSON objects')
  }
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${canonical(key)}:${canonical(value[key])}`)
    .join(',')}}`
}

export async function payloadReceipt(body: Json | null) {
  const payload_json = canonical(body)
  const bytes = new TextEncoder().encode(payload_json)
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  const payload_sha256 = [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
  return { payload_json, payload_sha256, payload_byte_length: bytes.byteLength }
}

export async function enqueueOutbox(
  row: Omit<OutboxRow, 'operation_id' | 'payload_json' | 'payload_sha256' | 'payload_byte_length'>,
): Promise<EnqueueResult | null> {
  const db = await outboxDatabase()
  if (!db) return null
  const receipt = await payloadReceipt(row.body)
  const stored = { ...row, ...receipt }
  let cancelled_rows: OutboxRow[] | undefined
  const operation_id = await db.transaction('rw', db.outbox, async () => {
    const rows = await db.outbox.orderBy('operation_id').toArray()
    const ownCreate = rows.find((item) => item.entity_id === row.entity_id && item.idempotency_mode === 'client_uuid')
    const parent = ownCreate ?? rows.find((item) => item.entity_id === row.parent_id && item.idempotency_mode === 'client_uuid')
    stored.dependency_operation_id ??= parent?.operation_id ?? null
    if (stored.dependency_operation_id && !rows.some((item) => item.operation_id === stored.dependency_operation_id)) {
      throw new Error('Outbox dependency must refer to an existing operation')
    }
    if (row.method === 'DELETE' && ownCreate) {
      const ids = descendantIds(rows, ownCreate.operation_id!)
      const tree = rows.filter((item) => ids.has(item.operation_id!))
      if (tree.every((item) => item.state === 'pending' && item.attempts === 0)) {
        await db.outbox.bulkDelete(tree.map((item) => item.operation_id!))
        cancelled_rows = tree
        cancelledReceipts.set(tree, structuredClone(tree))
        return undefined
      }
    }
    const previous = [...rows].reverse().find((item) => item.entity_id === row.entity_id && item.path === row.path &&
      item.operation_kind === row.operation_kind && item.requires_private === row.requires_private &&
      item.state === 'pending' && item.attempts === 0 && !rows.some((child) => child.dependency_operation_id === item.operation_id))
    if (row.method === 'PATCH' && row.idempotency_mode === 'absolute' && previous &&
      previous.body && row.body && !Array.isArray(previous.body) && !Array.isArray(row.body) &&
      typeof previous.body === 'object' && typeof row.body === 'object') {
      stored.body = { ...previous.body, ...row.body }
      Object.assign(stored, await Dexie.waitFor(payloadReceipt(stored.body)))
      await db.outbox.delete(previous.operation_id!)
    }
    return db.outbox.add(stored)
  })
  emitChanged()
  return { ...stored, operation_id, ...(cancelled_rows ? { cancelled_rows } : {}) }
}

/** Restore only an atomically cancelled, never-dispatched command tree. */
export async function restoreCancelledOutbox(rows: OutboxRow[]): Promise<OutboxRow[]> {
  const original = cancelledReceipts.get(rows)
  if (!original || JSON.stringify(rows) !== JSON.stringify(original)) throw new Error('Cancelled receipt changed or expired')
  const receipt = rows
  rows = structuredClone(original)
  const db = await outboxDatabase()
  if (!db) throw new Error('Cannot restore cancelled writes without durable storage')
  if (!rows.length || rows.some((row) => row.state !== 'pending' || row.attempts !== 0 || !row.operation_id)) throw new Error('Only never-dispatched commands can be restored')
  const receipts = await Promise.all(rows.map((row) => payloadReceipt(row.body)))
  if (rows.some((row, index) => row.payload_sha256 !== receipts[index].payload_sha256 || row.payload_json !== receipts[index].payload_json)) throw new Error('Cancelled payload changed')
  const restored = await db.transaction('rw', db.outbox, async () => {
    const existing = await db.outbox.toArray()
    if (existing.some((row) => rows.some((cancelled) => row.entity_id === cancelled.entity_id))) throw new Error('Entity already has queued changes')
    const orphaned = existing.filter((row) => row.dependency_operation_id === null && rows.some((parent) => parent.idempotency_mode === 'client_uuid' && parent.entity_id === row.parent_id))
    if (orphaned.some((row) => row.state !== 'pending' || row.attempts !== 0)) throw new Error('A dependent write needs reconciliation before undo')
    const ids = new Map<number, number>(), result: OutboxRow[] = []
    for (const row of rows) {
      const dependency = row.dependency_operation_id === null ? null : ids.get(row.dependency_operation_id)
      if (dependency === undefined) throw new Error('Cancelled dependency tree is incomplete')
      const item = { ...row, operation_id: undefined, dependency_operation_id: dependency, created_at: Date.now(), next_attempt_at: null, last_error_code: null }
      const id = await db.outbox.add(item)
      if (id === undefined) throw new Error('Durable operation ID was not assigned')
      ids.set(row.operation_id!, id)
      result.push({ ...item, operation_id: id })
    }
    for (const orphan of orphaned) {
      const parent = result.find((row) => row.idempotency_mode === 'client_uuid' && row.entity_id === orphan.parent_id)!
      await db.outbox.update(orphan.operation_id!, { dependency_operation_id: parent.operation_id, requires_private: orphan.requires_private || parent.requires_private })
    }
    return result
  })
  cancelledReceipts.delete(receipt)
  emitChanged()
  return restored
}

function descendantIds(rows: OutboxRow[], rootId: number) {
  const ids = new Set([rootId])
  for (const row of rows) {
    if (row.dependency_operation_id && ids.has(row.dependency_operation_id)) ids.add(row.operation_id!)
  }
  return ids
}

export async function claimOutbox(id: number): Promise<OutboxRow | null> {
  const db = await outboxDatabase()
  if (!db) return null
  return db.transaction('rw', db.outbox, async () => {
    const row = await db.outbox.get(id)
    if (!row || !['pending', 'outcome_unknown'].includes(row.state)) return null
    const claimed = { ...row, state: 'outcome_unknown' as const, attempts: row.attempts + 1 }
    await db.outbox.put(claimed)
    return claimed
  })
}

export async function listOutbox(): Promise<OutboxRow[]> {
  const db = await outboxDatabase()
  return db ? db.outbox.orderBy('operation_id').toArray() : []
}

export async function updateOutbox(id: number, changes: Partial<OutboxRow>) {
  const db = await outboxDatabase()
  if (!db) return
  const runtimeKeys = ['state', 'attempts', 'next_attempt_at', 'last_error_code']
  const mutable = Object.fromEntries(Object.entries(changes).filter(([key]) => runtimeKeys.includes(key))) as Partial<Pick<OutboxRow, 'state' | 'attempts' | 'next_attempt_at' | 'last_error_code'>>
  await db.outbox.update(id, mutable)
  emitChanged()
}

export async function removeOutbox(ids: number[]) {
  const db = await outboxDatabase()
  if (!db) return
  await db.outbox.bulkDelete(ids)
  emitChanged()
}

export async function discardOutboxTree(rootId: number): Promise<OutboxRow[]> {
  const rows = await listOutbox()
  const ids = descendantIds(rows, rootId)
  const discarded = rows.filter((row) => ids.has(row.operation_id!))
  await removeOutbox([...ids])
  return discarded
}
