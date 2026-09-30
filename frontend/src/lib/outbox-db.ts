import Dexie, { type EntityTable } from 'dexie'

export type Json = null | boolean | number | string | Json[] | { [key: string]: Json }
export type OutboxState =
  | 'pending'
  | 'auth_hold'
  | 'private_hold'
  | 'outcome_unknown'
  | 'failed'
  | 'suppressed'

export type OutboxRow = {
  operation_id?: number
  operation_kind: string
  resource: string
  method: 'POST' | 'PATCH' | 'DELETE'
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
}

type OutboxDb = Dexie & { outbox: EntityTable<OutboxRow, 'operation_id'> }
let database: OutboxDb | null = null
let unavailable = false

function emitChanged() {
  window.dispatchEvent(new Event('microsched:outbox-changed'))
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
    .map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`)
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
): Promise<OutboxRow | null> {
  const db = await outboxDatabase()
  if (!db) return null
  const receipt = await payloadReceipt(row.body)
  const stored = { ...row, ...receipt }
  const operation_id = await db.transaction('rw', db.outbox, async () => {
    if (row.idempotency_mode === 'absolute' && row.entity_id) {
      const older = await db.outbox.where('entity_id').equals(row.entity_id).toArray()
      const replaceable = older.filter(
        (item) =>
          item.operation_kind === row.operation_kind &&
          item.state === 'pending' &&
          item.attempts === 0,
      )
      if (replaceable.length) await db.outbox.bulkDelete(replaceable.map((item) => item.operation_id!))
    }
    return db.outbox.add(stored)
  })
  emitChanged()
  return { ...stored, operation_id }
}

export async function listOutbox(): Promise<OutboxRow[]> {
  const db = await outboxDatabase()
  return db ? db.outbox.orderBy('operation_id').toArray() : []
}

export async function updateOutbox(id: number, changes: Partial<OutboxRow>) {
  const db = await outboxDatabase()
  if (!db) return
  const immutable = { ...changes }
  delete immutable.payload_json
  delete immutable.payload_sha256
  delete immutable.payload_byte_length
  delete immutable.body
  await db.outbox.update(id, immutable)
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
  const ids = new Set([rootId])
  for (const row of rows) {
    if (row.dependency_operation_id && ids.has(row.dependency_operation_id)) ids.add(row.operation_id!)
  }
  const discarded = rows.filter((row) => ids.has(row.operation_id!))
  await removeOutbox([...ids])
  return discarded
}

export function resetOutboxAvailabilityForTests() {
  database?.close()
  database = null
  unavailable = false
}
