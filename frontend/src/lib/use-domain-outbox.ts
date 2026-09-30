import { useCallback, useEffect, useState } from 'react'
import { liveQuery } from 'dexie'
import type { QueryKey } from '@tanstack/react-query'

import { adapterFor } from '@/lib/outbox-adapters'
import { listOutbox, type OutboxRow } from '@/lib/outbox-db'

function keyContains(affected: unknown, queryKey: QueryKey): boolean {
  if (!Array.isArray(affected) || !Array.isArray(queryKey)) return false
  if (queryKey.length === 0) return true
  return affected.length <= queryKey.length &&
    affected.every((part, index) => JSON.stringify(part) === JSON.stringify(queryKey[index]))
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

export type DomainOutboxState = {
  rows: OutboxRow[]
  pendingCount: number
  failedCount: number
  unavailable: boolean
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
    const subscription = liveQuery(() => listOutbox()).subscribe({
      next: (next) => {
        setRows(next)
        setReadError(false)
      },
      error: () => setReadError(true),
    })
    const onChanged = () => { void refresh() }
    const onUnavailable = () => setUnavailable(true)
    window.addEventListener('microsched:outbox-changed', onChanged)
    window.addEventListener('microsched:offline-unavailable', onUnavailable)
    return () => {
      subscription.unsubscribe()
      window.removeEventListener('microsched:outbox-changed', onChanged)
      window.removeEventListener('microsched:offline-unavailable', onUnavailable)
    }
  }, [refresh])

  const visibleRows = rows.filter((row) => privateUnlocked || !row.requires_private || includePrivateMetadata)
  const relevant = visibleRows.filter((row) =>
    isUnknownOrMalformed(row) ||
    row.affected_query_keys.some((affected) => keyContains(affected, queryKey)),
  )
  return {
    rows: relevant,
    pendingCount: relevant.filter((row) => ['pending', 'outcome_unknown', 'auth_hold', 'private_hold'].includes(row.state)).length,
    failedCount: relevant.filter((row) => ['failed', 'suppressed'].includes(row.state)).length,
    unavailable,
    readError,
  }
}

/**
 * Domain query controls. Reconnect refetches are coordinator-owned; focus and
 * polling stop only while an affected command is waiting. Session queries must
 * not use this helper because they need to remain refreshable.
 */
type NormalInterval = number | false | ((query: { state: { status: string } }) => number | false)
export function useDomainReadControl(queryKey: QueryKey, normalInterval: NormalInterval, privateUnlocked = false) {
  const state = useDomainOutbox(queryKey, privateUnlocked)
  const blocked = state.pendingCount > 0 || state.failedCount > 0 || state.readError
  return {
    refetchOnMount: !blocked,
    refetchOnReconnect: false as const,
    refetchOnWindowFocus: !blocked,
    refetchInterval: blocked ? false : normalInterval,
    outbox: state,
  }
}
