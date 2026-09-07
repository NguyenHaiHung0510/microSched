export type FreshQuery = {
  status: string
  updatedAt: number
  paused: boolean
}

// Display tolerance only. Network intervals remain owned by query-polling.ts.
export const FRESH_WINDOW_MS = 30_000
export type FreshState = 'loading' | 'live' | 'stale' | 'error' | 'offline' | 'paused'

export function freshnessState(queries: FreshQuery[], now: number, online: boolean, visible: boolean): FreshState {
  if (!online) return 'offline'
  if (queries.some((query) => query.status === 'error')) return 'error'
  if (!queries.length || queries.some((query) => query.status !== 'success' || !query.updatedAt)) return 'loading'
  if (!visible || queries.some((query) => query.paused)) return 'paused'
  return queries.every((query) => now - query.updatedAt < FRESH_WINDOW_MS) ? 'live' : 'stale'
}
