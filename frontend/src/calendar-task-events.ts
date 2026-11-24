import type { QueryClient } from '@tanstack/react-query'
import { CALENDAR_TASKS_KEY } from '@/calendar-queries'
import type { MimiChangeSet, MimiReceipt } from '@/mimi-api'

const CHANNEL = 'microsched:task-commit:v1'
const LOCAL_EVENT = 'microsched-tasks-committed'
const DEDUP_LIMIT = 128
const COALESCE_MS = 50
const publishedReceipts = new Set<string>()
type CommitSignal = { version: 1; token: string }

function remember(seen: Set<string>, token: string): boolean {
  if (seen.has(token)) return false
  seen.add(token)
  if (seen.size > DEDUP_LIMIT) seen.delete(seen.values().next().value!)
  return true
}

function isSignal(value: unknown): value is CommitSignal {
  if (!value || typeof value !== 'object') return false
  const signal = value as Partial<CommitSignal>
  return signal.version === 1 && typeof signal.token === 'string' &&
    /^[0-9a-f-]{36}$/i.test(signal.token) && Object.keys(value).length === 2
}

// Called only after the authenticated decision/recovery API returns its durable
// receipt. Neither preview nor Reject/UNKNOWN is a committed Task projection.
export function publishMimiTaskCommit(change: Pick<MimiChangeSet, 'id' | 'digest'> & { operation: Pick<MimiChangeSet['operation'], 'operation_id' | 'tool'> }, receipt: MimiReceipt): void {
  if (typeof window === 'undefined' || !receipt ||
    !['task.create.v1', 'task.collection.v1'].includes(change.operation.tool) ||
    !receipt.id || !receipt.executed_at || receipt.change_set_id !== change.id ||
    receipt.digest !== change.digest || receipt.operation_id !== change.operation.operation_id ||
    !remember(publishedReceipts, receipt.id)) return

  // No receipt/Task/conversation IDs, prose, fields or private payload leave the
  // current tab. A signal only asks other tabs to re-read their own auth scope.
  const signal: CommitSignal = { version: 1, token: crypto.randomUUID() }
  window.dispatchEvent(new CustomEvent(LOCAL_EVENT, { detail: signal }))
  let channel: BroadcastChannel | undefined
  try {
    channel = new window.BroadcastChannel(CHANNEL)
    channel.postMessage(signal)
    return
  } catch { /* Restricted/older browsers use one overwrite-only storage key. */ }
  finally { channel?.close() }
  try { window.localStorage.setItem(CHANNEL, JSON.stringify(signal)) }
  catch { /* Focus/visibility/reconnect still reconcile if both transports fail. */ }
}

/** One subscriber per mounted Calendar, disposed with its screen. No interval. */
export function subscribeCalendarTaskCommits(client: QueryClient): () => void {
  const seen = new Set<string>()
  let timer: ReturnType<typeof setTimeout> | undefined
  let disposed = false
  const canRefetch = () => document.visibilityState !== 'hidden' && window.navigator.onLine !== false
  const invalidate = (refetchType: 'none' | 'active') => {
    for (const queryKey of [CALENDAR_TASKS_KEY, ['tasks']] as const) {
      // Invalidation alone reuses a cold in-flight read. Cancel it first so a
      // response started before commit cannot settle as the current projection.
      if (refetchType === 'active') void client.cancelQueries({ queryKey, type: 'active' })
      void client.invalidateQueries({ queryKey, refetchType })
    }
  }
  const schedule = () => {
    if (disposed || timer !== undefined || !canRefetch()) return
    timer = setTimeout(() => {
      timer = undefined
      if (!disposed && canRefetch()) invalidate('active')
    }, COALESCE_MS)
  }
  const receive = (value: unknown) => {
    if (!isSignal(value) || !remember(seen, value.token)) return
    invalidate('none') // Hidden/inactive ranges stay stale until used again.
    schedule()
  }
  const local = (event: Event) => receive((event as CustomEvent<unknown>).detail)
  const storage = (event: StorageEvent) => {
    if (event.key !== CHANNEL || !event.newValue || event.newValue.length > 128) return
    try { receive(JSON.parse(event.newValue)) } catch { /* Ignore unrelated/bad signals. */ }
  }
  const reconcile = () => {
    if (!canRefetch()) return
    invalidate('none') // Also repairs missed events after a sleeping/offline tab.
    schedule()
  }
  let channel: BroadcastChannel | undefined
  try {
    channel = new window.BroadcastChannel(CHANNEL)
    channel.onmessage = (event: MessageEvent<unknown>) => receive(event.data)
  } catch { /* Storage events and lifecycle reconciliation remain available. */ }
  window.addEventListener(LOCAL_EVENT, local)
  window.addEventListener('storage', storage)
  window.addEventListener('focus', reconcile)
  window.addEventListener('online', reconcile)
  document.addEventListener('visibilitychange', reconcile)
  return () => {
    disposed = true
    if (timer !== undefined) clearTimeout(timer)
    window.removeEventListener(LOCAL_EVENT, local)
    window.removeEventListener('storage', storage)
    window.removeEventListener('focus', reconcile)
    window.removeEventListener('online', reconcile)
    document.removeEventListener('visibilitychange', reconcile)
    channel?.close()
  }
}
