/** V1 persists typed intent, never a request URL or credentials. */
export const KINDS = ['task.create','task.update','task.delete','task.restore',
  'task_item.create','task_item.update','task_item.delete',
  'entry.create','entry.update','entry.delete','entry.restore'] as const
export type Kind = typeof KINDS[number]
export type Fields = Record<string, unknown>
export type Command = {
  version: 1; id: string; operation_id?: number; principal: string; kind: Kind
  entity: string; parent: string; aggregate: string; predecessor: string | null
  dependency: string | null; created_at: string; expires_at: number
  payload: string; digest: string; envelope_digest: string; invalid?: boolean; byte_length: number; requires_private: boolean
  state: 'pending' | 'sending' | 'unknown' | 'rejected' | 'held'
  attempted: boolean; attempt: number; next_due: number; transport_until?: number; reason: string
}
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
export function validId(value: unknown): value is string { return typeof value === 'string' && uuid.test(value) }
export function canonical(value: unknown): string {
  if (value === null || typeof value !== 'object') {
    if (typeof value === 'number' && !Number.isFinite(value)) throw new Error('Invalid number')
    if (value === undefined) throw new Error('Undefined command field')
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']'
  return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical((value as Fields)[k])).join(',') + '}'
}
export async function hash(value: string): Promise<string> {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))
  return Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, '0')).join('')
}
const fields: Record<Kind, readonly string[]> = {
  'task.create': ['id','title','body_md','status','priority','due_precision','due_on','due_at','is_private','items','item_ids'],
  'task.update': ['title','body_md','status','priority','due_precision','due_on','due_at','is_private','pinned'],
  'task.delete': [], 'task.restore': [],
  'task_item.create': ['id','content','position'],
  'task_item.update': ['content','is_completed','position'], 'task_item.delete': [],
  'entry.create': ['id','tracker_id','occurred_at','quantity','amount','list_amount','note_md'],
  'entry.update': ['occurred_at','quantity','amount','list_amount','note_md'],
  'entry.delete': [], 'entry.restore': [],
}
export function validatePayload(kind: Kind, entity: string, parent: string, payload: Fields): void {
  if (!KINDS.includes(kind) || !validId(entity) || !validId(parent)) throw new Error('Lệnh không được hỗ trợ')
  if (!payload || Array.isArray(payload) || Object.keys(payload).some(k => !fields[kind].includes(k))) throw new Error('Trường lệnh không hợp lệ')
  if (kind.startsWith('task.') && entity !== parent) throw new Error('Task aggregate identity mismatch')
  if (kind.endsWith('.create') && payload.id !== entity) throw new Error('Client identity mismatch')
  if (kind === 'entry.create' && payload.tracker_id !== parent) throw new Error('Tracker identity mismatch')
  if (kind === 'task.create') {
    if (typeof payload.title !== 'string' || !payload.title.trim()) throw new Error('Thiếu tên task')
    const items = payload.items as unknown[], ids = payload.item_ids as unknown[]
    if (!Array.isArray(items) || !Array.isArray(ids) || items.length !== ids.length ||
      ids.some(id => !validId(id)) || new Set(ids).size !== ids.length ||
      items.some(item => typeof item !== 'string' || !item.trim())) throw new Error('Checklist identity mismatch')
  }
  if (kind === 'task_item.create' && (typeof payload.content !== 'string' || !payload.content.trim())) throw new Error('Thiếu nội dung')
  if (kind === 'entry.create' && (typeof payload.occurred_at !== 'string' || !Number.isFinite(Date.parse(payload.occurred_at)))) throw new Error('Thiếu giờ ghi gốc')
}
export async function decode(row: Command): Promise<Fields> {
  if (row.version !== 1 || !validId(row.id) || !row.principal || !KINDS.includes(row.kind)) throw new Error('Định dạng chưa được hỗ trợ')
  const body: unknown = JSON.parse(row.payload)
  if (!body || typeof body !== 'object' || Array.isArray(body)) throw new Error('Invalid payload')
  validatePayload(row.kind, row.entity, row.parent, body as Fields)
  if (row.aggregate !== (row.kind.startsWith('entry.') ? 'tracker:' + row.parent : 'task:' + row.parent) ||
    canonical(body) !== row.payload || new TextEncoder().encode(row.payload).length !== row.byte_length ||
    await hash(row.payload) !== row.digest ||
    await hash(canonical({version:row.version,id:row.id,principal:row.principal,kind:row.kind,entity:row.entity,parent:row.parent,aggregate:row.aggregate,payload:row.payload})) !== row.envelope_digest) throw new Error('Lệnh cần kiểm tra tính toàn vẹn')
  return body as Fields
}
export function route(row: Pick<Command, 'kind'|'entity'|'parent'>): { path: string; method: string } {
  if (!KINDS.includes(row.kind) || !validId(row.entity) || !validId(row.parent)) throw new Error('Invalid typed route')
  const {kind,entity,parent} = row
  if (kind.startsWith('task_item.')) return {
    path: '/api/tasks/' + parent + '/items' + (kind === 'task_item.create' ? '' : '/' + entity),
    method: kind === 'task_item.create' ? 'POST' : kind === 'task_item.update' ? 'PATCH' : 'DELETE',
  }
  const base = kind.startsWith('entry.') ? '/api/tracker/entries' : '/api/tasks'
  const action = kind.split('.')[1]
  return {path: base + (action === 'create' ? '' : '/' + entity) + (action === 'restore' ? '/restore' : ''),
    method: action === 'create' || action === 'restore' ? 'POST' : action === 'update' ? 'PATCH' : 'DELETE'}
}
export function retryDelay(attempt: number, header: string | null, now = Date.now()): number {
  const parsed = header === null ? NaN : Number(header)
  const server = header === null ? 0 : Number.isFinite(parsed) ? parsed * 1000 : Date.parse(header) - now
  return Math.max(Math.min(30_000, 1000 * 2 ** Math.min(Math.max(attempt - 1, 0), 5)), Number.isFinite(server) ? server : 0)
}
export const TOMBSTONES: Partial<Record<Kind,string>> = {
  'task.delete':'TASK_ALREADY_DELETED', 'task_item.delete':'TASK_ITEM_ALREADY_DELETED', 'entry.delete':'ENTRY_ALREADY_DELETED',
}
