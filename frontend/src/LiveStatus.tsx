import { onlineManager, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'
import { cn } from '@/lib/utils'
import { freshnessState, FRESH_WINDOW_MS, type FreshQuery } from '@/freshness'

const labels = {
  loading: 'Đang tải dữ liệu…',
  live: 'live and fresh',
  stale: 'Dữ liệu chưa cập nhật',
  error: 'Cập nhật bị gián đoạn',
  offline: 'Đang offline',
  paused: 'Tạm dừng cập nhật',
}

export function LiveStatus({ tab }: { tab: 'tasks' | 'notes' | 'tracker' }) {
  const cache = useQueryClient().getQueryCache()
  const subscribe = useCallback((notify: () => void) => cache.subscribe(notify), [cache])
  const snapshot = useCallback(() => JSON.stringify(cache.getAll()
    .filter((query) => query.getObserversCount() > 0 && (
      query.queryKey[0] === tab || (tab === 'tracker' && query.queryKey[0] === 'subscription')
    ))
    .map((query) => ({ status: query.state.status, updatedAt: query.state.dataUpdatedAt, paused: query.state.fetchStatus === 'paused' }))), [cache, tab])
  const serialized = useSyncExternalStore(subscribe, snapshot)
  const online = useSyncExternalStore(onlineManager.subscribe, () => onlineManager.isOnline())
  const [visible, setVisible] = useState(() => document.visibilityState !== 'hidden')
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const update = () => { setVisible(document.visibilityState !== 'hidden'); setNow(Date.now()) }
    document.addEventListener('visibilitychange', update)
    return () => document.removeEventListener('visibilitychange', update)
  }, [])
  useEffect(() => {
    const queries = JSON.parse(serialized) as FreshQuery[]
    const deadline = Math.min(...queries.filter((query) => query.updatedAt > 0).map((query) => query.updatedAt + FRESH_WINDOW_MS))
    // One local expiry timeout per data snapshot, no network request or repeating clock.
    const timer = window.setTimeout(() => setNow(Date.now()), 0)
    const expiry = Number.isFinite(deadline) && deadline > Date.now() && visible
      ? window.setTimeout(() => setNow(Date.now()), deadline - Date.now() + 1) : undefined
    return () => { window.clearTimeout(timer); window.clearTimeout(expiry) }
  }, [serialized, visible])
  const state = freshnessState(JSON.parse(serialized) as FreshQuery[], now, online, visible)
  return (
    <span data-testid="app-live-status" data-state={state} role="status"
      className={cn('inline-flex max-w-full items-center gap-1.5 text-xs font-semibold', state === 'live' ? 'text-ok' : state === 'error' ? 'text-bad' : 'text-muted-foreground')}>
      <span aria-hidden="true" className={cn('size-2 shrink-0 rounded-full', state === 'live' ? 'bg-ok' : state === 'error' ? 'bg-bad' : 'bg-muted-foreground')} />
      {labels[state]}
    </span>
  )
}
