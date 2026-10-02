/// <reference types="vite/client" />
import {
  persistQueryClientRestore,
  persistQueryClientSubscribe,
  type PersistedClient,
  type Persister,
} from '@tanstack/query-persist-client-core'
import { dehydrate, type QueryClient } from '@tanstack/react-query'
import { listOutbox, type OutboxRow } from '@/lib/outbox-db'
import { clearOutboxBaselines } from '@/lib/outbox-adapters'

const DB_NAME = 'microsched-public-cache'
const STORE = 'snapshots'
const CACHE_KEY = 'query-client'
const BOOTSTRAP_KEY = 'session-bootstrap'
export const QUERY_MAX_AGE = 7 * 24 * 60 * 60 * 1000
export const CACHE_BUSTER = import.meta.env.VITE_GIT_SHA || 'development'

export type SessionBootstrap = {
  email: string
  signed_in_at: string | null
  expires_at: string
  last_verified: true
}

function openCacheDb(): Promise<IDBDatabase> {
  return new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1)
    request.onupgradeneeded = () => request.result.createObjectStore(STORE)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function read<T>(key: string): Promise<T | undefined> {
  const db = await openCacheDb()
  return new Promise<T | undefined>((resolve, reject) => {
    const request = db.transaction(STORE).objectStore(STORE).get(key)
    request.onsuccess = () => resolve(request.result as T | undefined)
    request.onerror = () => reject(request.error)
  }).finally(() => db.close())
}

async function write(key: string, value: unknown) {
  const db = await openCacheDb()
  return new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(STORE, 'readwrite')
    transaction.objectStore(STORE).put(value, key)
    transaction.oncomplete = () => resolve()
    transaction.onabort = () => reject(transaction.error)
    transaction.onerror = () => reject(transaction.error)
  }).finally(() => db.close())
}

async function remove(keys: string[]) {
  const db = await openCacheDb()
  return new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(STORE, 'readwrite')
    for (const key of keys) transaction.objectStore(STORE).delete(key)
    transaction.oncomplete = () => resolve()
    transaction.onabort = () => reject(transaction.error)
    transaction.onerror = () => reject(transaction.error)
  }).finally(() => db.close())
}

type PersistedQuery = PersistedClient['clientState']['queries'][number]

function keyOf(query: PersistedQuery): readonly unknown[] {
  return Array.isArray(query.queryKey) ? query.queryKey : []
}

type PersistedEntity = Record<string, unknown>

function envelope(data: unknown): { items: PersistedEntity[] } | null {
  return data &&
    typeof data === 'object' &&
    'items' in data &&
    Array.isArray(data.items)
    ? (data as { items: PersistedEntity[] })
    : null
}

export function sanitizePersistedClient(client: PersistedClient): PersistedClient {
  const next = structuredClone(client)
  const queries = next.clientState.queries
  const trackerIds = new Set<string>()
  const groupCounts = new Map<string, number>()
  for (const query of queries) {
    const key = keyOf(query)
    if (key[0] !== 'tracker' || key[1] !== 'trackers') continue
    for (const tracker of envelope(query.state.data)?.items ?? []) {
      if (tracker.is_private !== false || typeof tracker.id !== 'string') continue
      trackerIds.add(tracker.id)
      if (typeof tracker.group_id === 'string') {
        groupCounts.set(tracker.group_id, (groupCounts.get(tracker.group_id) ?? 0) + 1)
      }
    }
  }
  next.clientState.queries = queries.flatMap((query) => {
    const key = keyOf(query)
    if (query.state.status !== 'success') return []
    const data = structuredClone(query.state.data)
    const list = envelope(data)
    const publicItems = (items: PersistedEntity[]) => items.filter((item) => item.is_private === false)
    let safe: unknown
    if (key[0] === 'notes' && key.length === 1 && Array.isArray(data)) {
      safe = publicItems(data)
    } else if (key[0] === 'tasks' && ['all', 'open', 'completed', 'timeline'].includes(String(key[1]))) {
      if (Array.isArray(data)) safe = publicItems(data)
      else if (list) {
        safe = key[1] === 'timeline'
          ? { items: publicItems(list.items), counts: {}, next_cursor: null, bucket_cursors: {}, has_previous: false, has_next: false, loaded_range_start: (data as Record<string, unknown>).loaded_range_start, loaded_range_end: (data as Record<string, unknown>).loaded_range_end }
          : { items: publicItems(list.items) }
      } else return []
    } else if (key[0] === 'calendar' && ['tasks', 'annotations'].includes(String(key[1]))) {
      if (key[1] === 'tasks' && Array.isArray(data)) safe = publicItems(data)
      else if (list) safe = { items: publicItems(list.items) }
      else return []
    } else if (key[0] === 'calendar' && ['sources', 'events'].includes(String(key[1]))) {
      if (!list) return []
      safe = { items: list.items }
    } else if (key[0] === 'tracker' && key[1] === 'trackers') {
      if (!list) return []
      safe = { items: publicItems(list.items) }
    } else if (key[0] === 'tracker' && key[1] === 'groups') {
      if (!list) return []
      safe = { items: list.items.map((group) => ({
        ...group, tracker_count: typeof group.id === 'string' ? groupCounts.get(group.id) ?? 0 : 0,
      })) }
    } else if ((key[0] === 'tracker' && key[1] === 'entries') ||
      (key[0] === 'subscription' && key[1] === 'subscriptions')) {
      if (!list) return []
      safe = { items: list.items.filter((item) =>
        typeof item.tracker_id === 'string' && trackerIds.has(item.tracker_id)) }
    } else if (key[0] === 'subscription' && key[1] === 'settings') {
      if (!list) return []
      const allowed = new Set(['show_list_price', 'subscription_expiry_lead_days'])
      safe = { items: list.items.filter((item) => typeof item.key === 'string' && allowed.has(item.key)) }
    } else return []
    return [{ ...query, state: { ...query.state, data: safe, error: null, fetchFailureReason: null, fetchMeta: null } }]
  })
  next.clientState.mutations = []
  return next
}
export function preserveConfirmedBaseline(
  current: PersistedClient, previous: PersistedClient | undefined,
  pending: Pick<OutboxRow, 'affected_query_keys'>[],
): PersistedClient {
  const compatible = previous?.buster === current.buster &&
    current.timestamp - previous.timestamp <= QUERY_MAX_AGE ? previous : undefined
  const overlaps = (key: readonly unknown[]) => pending.some((row) =>
    row.affected_query_keys.some((affected) => affected.slice(0, Math.min(key.length, affected.length))
      .every((part, index) => JSON.stringify(part) === JSON.stringify(key[index]))))
  const queries = new Map(current.clientState.queries.filter((query) => !overlaps(keyOf(query)))
    .map((query) => [query.queryHash, query]))
  for (const query of compatible?.clientState.queries ?? []) {
    if (overlaps(keyOf(query))) queries.set(query.queryHash, query)
  }
  return sanitizePersistedClient({ ...current, clientState: {
    mutations: [], queries: [...queries.values()],
  } })
}

let persistenceJobs = Promise.resolve()
let persistenceEpoch = 0
async function persistConfirmedClient(client: PersistedClient) {
  const snapshot = structuredClone(client)
  const epoch = persistenceEpoch
  const job = persistenceJobs.catch(() => undefined).then(async () => {
    if (epoch !== persistenceEpoch) return
    const [previous, pending] = await Promise.all([read<PersistedClient>(CACHE_KEY), listOutbox()])
    await write(CACHE_KEY, preserveConfirmedBaseline(snapshot, previous, pending))
  })
  persistenceJobs = job
  return job
}

export async function persistConfirmedSnapshot(client: QueryClient) {
  await persistConfirmedClient({ buster: CACHE_BUSTER, timestamp: Date.now(), clientState: dehydrate(client) })
}

const persister: Persister = {
  persistClient: persistConfirmedClient,
  restoreClient: async () => {
    const saved = await read<PersistedClient>(CACHE_KEY)
    return saved ? sanitizePersistedClient(saved) : undefined
  },
  removeClient: async () => {
    persistenceEpoch += 1
    await persistenceJobs.catch(() => undefined)
    await remove([CACHE_KEY])
  },
}

export async function initializePublicPersistence(client: QueryClient) {
  try {
    await persistQueryClientRestore({
      queryClient: client,
      persister,
      maxAge: QUERY_MAX_AGE,
      buster: CACHE_BUSTER,
    })
    return persistQueryClientSubscribe({ queryClient: client, persister, buster: CACHE_BUSTER })
  } catch {
    window.dispatchEvent(new Event('microsched:offline-unavailable'))
    return () => undefined
  }
}

export async function saveSessionBootstrap(session: SessionBootstrap) {
  await write(BOOTSTRAP_KEY, {
    email: session.email, signed_in_at: session.signed_in_at,
    expires_at: session.expires_at, last_verified: true,
  } satisfies SessionBootstrap)
}

export async function publicSnapshotTimestamp(): Promise<number | null> {
  try { return (await read<PersistedClient>(CACHE_KEY))?.timestamp ?? null } catch { return null }
}

export async function loadSessionBootstrap(): Promise<SessionBootstrap | null> {
  try {
    const snapshot = await read<SessionBootstrap>(BOOTSTRAP_KEY)
    return snapshot?.last_verified && Date.parse(snapshot.expires_at) > Date.now() ? snapshot : null
  } catch {
    return null
  }
}

export async function purgePrivateSurface(client: QueryClient, full = false) {
  clearOutboxBaselines(client, full)
  if (full) {
    persistenceEpoch += 1
    client.clear()
    await persistenceJobs.catch(() => undefined)
    await remove([CACHE_KEY, BOOTSTRAP_KEY])
    return
  }
  const dehydrated: PersistedClient = {
    buster: CACHE_BUSTER,
    timestamp: Date.now(),
    clientState: { mutations: [], queries: client.getQueryCache().getAll().map((query) => ({
      dehydratedAt: Date.now(),
      state: query.state,
      queryKey: query.queryKey,
      queryHash: query.queryHash,
    })) },
  }
  const safe = sanitizePersistedClient(dehydrated)
  const allowed = new Map(safe.clientState.queries.map((query) => [query.queryHash, query.state.data]))
  for (const query of client.getQueryCache().getAll()) {
    if (allowed.has(query.queryHash)) client.setQueryData(query.queryKey, allowed.get(query.queryHash))
    else if (query.queryKey[0] !== 'session') client.removeQueries({ queryKey: query.queryKey, exact: true })
  }
  await persister.persistClient(safe)
}

export const PUBLIC_CACHE_DB_NAME = DB_NAME
