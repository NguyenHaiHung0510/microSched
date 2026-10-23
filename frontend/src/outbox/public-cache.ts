import Dexie, { type Table } from 'dexie'
import type { QueryClient, QueryKey } from '@tanstack/react-query'
import { persistQueryClientRestore, persistQueryClientSubscribe, type PersistedClient, type Persister } from '@tanstack/query-persist-client-core'
import type { BootstrapSession } from './types'
import { hash, type Fields } from './protocol'

type Bootstrap = {id: 'bootstrap'; principal: string; expires: number; saved: number}
type Snapshot = {id: string; value: PersistedClient}
class PublicCache extends Dexie {
  meta!: Table<Bootstrap,string>
  snapshots!: Table<Snapshot,string>
  constructor() { super('microsched-public-cache-v1'); this.version(1).stores({meta:'id',snapshots:'id'}) }
}
const cache = new PublicCache()
export const MAX_AGE = 7 * 86400_000
let principal = '', expires = 0, epoch = 0, subscribed = false
export let snapshotAt = 0
const buster = 'public-v1'
export async function purgePublicCache(keepBootstrap = false): Promise<void> {
  epoch++
  await cache.transaction('rw',cache.meta,cache.snapshots,async () => { if (!keepBootstrap) await cache.meta.clear(); await cache.snapshots.clear() })
}
export async function saveBootstrap(session: BootstrapSession, current = () => true): Promise<string> {
  const startEpoch = epoch
  const next = await hash(session.email.trim().toLowerCase())
  if(startEpoch!==epoch || !current()) return next
  if (principal && principal !== next) await purgePublicCache()
  const previous = await cache.meta.get('bootstrap')
  if(!current()) return next
  if (previous && previous.principal !== next) await purgePublicCache()
  if(!current()) return next
  principal = next
  expires = Math.min(Date.parse(session.expires_at),Date.now()+MAX_AGE)
  const commitEpoch=epoch
  await cache.transaction('rw',cache.meta,async () => {
    if(commitEpoch!==epoch || !current())return
    await cache.meta.put({id:'bootstrap',principal,expires,saved:Date.now()})
  })
  return next
}
export async function offlineBootstrap(): Promise<BootstrapSession | null> {
  const record = await cache.meta.get('bootstrap')
  if (!record || record.expires <= Date.now() || record.saved + MAX_AGE <= Date.now()) return null
  principal = record.principal; expires = record.expires; snapshotAt = record.saved
  return {email:'',signed_in_at:null,expires_at:new Date(expires).toISOString(),mimi_available:false,
    private_until:null,private_locked_until:null,pin_is_set:false,pin_is_bootstrap:false,offline_bootstrap:true,principal}
}
const obj = (v: unknown): v is Fields => !!v && typeof v === 'object' && !Array.isArray(v)
function items(data: unknown): Fields[] {
  const array = Array.isArray(data) ? data : obj(data) && Array.isArray(data.items) ? data.items : []
  return array.filter(obj)
}
function publicTask(row: Fields): boolean {
  return row.is_private === false && typeof row.id === 'string' && typeof row.title === 'string' && Array.isArray(row.items)
}
export function sanitizeSnapshot(value: PersistedClient): PersistedClient {
  const queries = value.clientState.queries
  const trackerQueries = queries.filter(q => q.queryKey[0] === 'tracker' && q.queryKey[1] === 'trackers')
  const publicTrackers = new Map<string,Fields>()
  let visibilityAt = 0
  for (const query of trackerQueries) {
    visibilityAt = Math.max(visibilityAt,query.state.dataUpdatedAt)
    for (const row of items(query.state.data)) if (row.is_private === false && typeof row.id === 'string') publicTrackers.set(row.id,row)
  }
  const safe = queries.flatMap(query => {
    const key = query.queryKey, data = query.state.data
    let rows: Fields[]
    if (key[0] === 'tasks' && ['all','open','completed','timeline','overdue-before'].includes(String(key[1])) || key[0] === 'calendar' && key[1] === 'tasks') rows = items(data).filter(publicTask)
    else if (key[0] === 'tracker' && key[1] === 'trackers') rows = items(data).filter(r => r.is_private === false)
    else if (key[0] === 'tracker' && key[1] === 'groups') rows = items(data).map(row => ({
      ...row, tracker_count: [...publicTrackers.values()].filter(t => t.group_id === row.id).length,
    }))
    else if (key[0] === 'tracker' && key[1] === 'entries' && visibilityAt >= query.state.dataUpdatedAt)
      rows = items(data).filter(row => publicTrackers.has(String(row.tracker_id)))
    else return []
    // Never serialize a projected graph, mixed-private totals, continuation cursor or session.
    const clean = Array.isArray(data) ? rows : {items:rows,next_cursor:null,snapshot_partial:true,
      ...(key[1] === 'timeline' ? {bucket_cursors:{overdue:null,dated:null,undated:null},bucket_counts:{
        overdue:0,dated:rows.filter(r => r.due_precision !== 'none').length,undated:rows.filter(r => r.due_precision === 'none').length,
      },has_previous:false,has_next:false} : {})}
    return [{...query,state:{...query.state,data:clean}}]
  })
  return {...value,clientState:{mutations:[],queries:safe}}
}
function persister(): Persister {
  return {
    async persistClient(value) {
      if (!principal || Date.now() >= expires) return
      const startEpoch = epoch, owner = principal
      const safe = sanitizeSnapshot(value)
      if (startEpoch !== epoch || owner !== principal) return
      await cache.transaction('rw',cache.snapshots,async () => {
        if (startEpoch !== epoch || owner !== principal) return
        await cache.snapshots.put({id:owner,value:safe})
      }).catch(() => {})
      snapshotAt = value.timestamp
    },
    async restoreClient() {
      if (!principal || expires <= Date.now()) return undefined
      const stored = await cache.snapshots.get(principal)
      return stored?.value
    },
    async removeClient() { if (principal) await cache.snapshots.delete(principal) },
  }
}
export async function restorePublicQueries(client: QueryClient): Promise<void> {
  try {
    await offlineBootstrap()
    await persistQueryClientRestore({queryClient:client,persister:persister(),maxAge:MAX_AGE,buster})
    if (!subscribed) {
      subscribed = true
      persistQueryClientSubscribe({queryClient:client,persister:persister(),buster,dehydrateOptions:{
        shouldDehydrateMutation:() => false,
        shouldDehydrateQuery:q => q.state.status === 'success' &&
          (q.queryKey[0] === 'tasks' || q.queryKey[0] === 'calendar' && q.queryKey[1] === 'tasks' || q.queryKey[0] === 'tracker' && ['groups','trackers','entries'].includes(String(q.queryKey[1]))),
      }})
    }
  } catch { /* Public snapshots are optional; command admission reports its own storage failure. */ }
}
export function isCanonicalFamily(key: QueryKey): boolean { return key[0] === 'tasks' || key[0] === 'tracker' || key[0] === 'calendar' }
