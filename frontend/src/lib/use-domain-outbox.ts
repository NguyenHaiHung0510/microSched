import { useCallback, useEffect, useState } from 'react'
import { liveQuery } from 'dexie'
import type { QueryKey } from '@tanstack/react-query'

import { adapterFor, requiresPrivateRow } from '@/lib/outbox-adapters'
import { listOutbox, outboxDatabase, type OutboxRow } from '@/lib/outbox-db'

export function isAffectedQueryKey(affected: unknown, queryKey: QueryKey): boolean {
  if (!Array.isArray(affected) || !Array.isArray(queryKey)) return false
  if (queryKey.length === 0) return true
  const sharedLength = Math.min(affected.length, queryKey.length)
  return affected.slice(0, sharedLength).every((part, index) => JSON.stringify(part) === JSON.stringify(queryKey[index]))
}

function isUnknownOrMalformed(row: OutboxRow): boolean {
  try {
    const adapter = adapterFor(row.operation_kind)
    return adapter.resource !== row.resource ||
      !Array.isArray(row.affected_query_keys) || row.affected_query_keys.length === 0
  } catch {
    return true
  }
}

export function isWebLocksCapabilityMissing(locksAvailable: boolean, secureContext: boolean) {
  return !locksAvailable || !secureContext
}

export function subscribeOutboxBroadcast(onChanged: () => void): () => void {
  if (typeof BroadcastChannel === 'undefined') return () => undefined
  try {
    const channel = new BroadcastChannel('microsched-outbox-events')
    channel.onmessage = (event: MessageEvent<unknown>) => {
      if (event.data === 'changed') onChanged()
    }
    return () => channel.close()
  } catch {
    return () => undefined
  }
}

export type DomainOutboxState = {
  rows: OutboxRow[]
  pendingCount: number
  failedCount: number
  unavailable: boolean
  webLocksUnavailable: boolean
  readError: boolean
}

/** Read-only queue status for domain UI. It does not flush or mutate rows. */
export function useDomainOutbox(
  queryKey: QueryKey,
  privateUnlocked = false,
  includePrivateMetadata = false,
): DomainOutboxState {
  const [rows, setRows] = useState<OutboxRow[]>([])
  const [unavailable, setUnavailable] = useState(false)
  const [webLocksUnavailable, setWebLocksUnavailable] = useState(() =>
    isWebLocksCapabilityMissing(
      typeof navigator !== 'undefined' && 'locks' in navigator,
      typeof window !== 'undefined' && window.isSecureContext === true,
    ),
  )
  const [readError, setReadError] = useState(false)

  const refresh = useCallback(() => {
    void listOutbox().then((next) => {
      setRows(next)
      setReadError(false)
    }).catch(() => {
      setReadError(true)
    })
  }, [])

  useEffect(() => {
    // Force the first durable read now so an initial IndexedDB open failure is
    // reflected even when its one-shot event fired before this component mounted.
    void outboxDatabase().then((db) => {
      if (!db) setUnavailable(true)
    })
    void listOutbox().then((next) => {
      setRows(next)
      setReadError(false)
    }).catch(() => setReadError(true))
    const subscription = liveQuery(() => listOutbox()).subscribe({
      next: (next) => {
        setRows(next)
        setReadError(false)
      },
      error: () => setReadError(true),
    })
    const onChanged = () => { void refresh() }
    const onUnavailable = () => setUnavailable(true)
    const onWebLocksUnavailable = () => setWebLocksUnavailable(true)
    const closeChannel = subscribeOutboxBroadcast(refresh)
    window.addEventListener('microsched:outbox-changed', onChanged)
    window.addEventListener('microsched:offline-unavailable', onUnavailable)
    window.addEventListener('microsched:web-locks-unavailable', onWebLocksUnavailable)
    return () => {
      subscription.unsubscribe()
      closeChannel()
      window.removeEventListener('microsched:outbox-changed', onChanged)
      window.removeEventListener('microsched:offline-unavailable', onUnavailable)
      window.removeEventListener('microsched:web-locks-unavailable', onWebLocksUnavailable)
    }
  }, [refresh])

  const visibleRows = rows.filter((row) => privateUnlocked || !requiresPrivateRow(row) || includePrivateMetadata)
  const relevant = visibleRows.filter((row) =>
    isUnknownOrMalformed(row) ||
    row.affected_query_keys.some((affected) => isAffectedQueryKey(affected, queryKey)),
  )
  return {
    rows: relevant,
    pendingCount: relevant.filter((row) => ['pending', 'outcome_unknown', 'auth_hold', 'private_hold'].includes(row.state)).length,
    failedCount: relevant.filter((row) => ['failed', 'suppressed'].includes(row.state)).length,
    unavailable,
    webLocksUnavailable,
    readError,
  }
}

/**
 * Domain query controls. Reconnect refetches are coordinator-owned; focus and
 * polling stop only while an affected command is waiting. Session queries must
 * not use this helper because they need to remain refreshable.
 */
type NormalInterval = number | false | ((query: { state: { status: string } }) => number | false)
export function domainReadOptions(blocked: boolean, normalInterval: NormalInterval) {
  return {
    refetchOnMount: !blocked,
    refetchOnReconnect: false as const,
    refetchOnWindowFocus: !blocked,
    refetchInterval: blocked ? false : normalInterval,
  }
}

export function useDomainReadControl(
  queryKey: QueryKey,
  normalInterval: NormalInterval,
  privateUnlocked = false,
  includePrivateForReadControl = false,
) {
  const state = useDomainOutbox(queryKey, privateUnlocked, includePrivateForReadControl)
  const blocked = state.pendingCount > 0 || state.failedCount > 0 || state.readError
  return {
    ...domainReadOptions(blocked, normalInterval),
    outbox: includePrivateForReadControl && !privateUnlocked
      ? { ...state, rows: state.rows.filter((row) => !requiresPrivateRow(row)) }
      : state,
  }
}
