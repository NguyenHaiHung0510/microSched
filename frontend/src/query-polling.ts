export const TASK_REFETCH_MS = 1_000
export const STANDARD_REFETCH_MS = 15_000

type QueryWithStatus = {
  state: { status: string }
}

export const APP_QUERY_DEFAULTS = Object.freeze({
  // Polling is opt-in. A new query must not silently inherit a live timer.
  refetchInterval: false,
  refetchIntervalInBackground: false,
  refetchOnMount: true,
  refetchOnWindowFocus: true,
} as const)

export const NO_POLLING_QUERY_OPTIONS = Object.freeze({
  refetchInterval: false,
} as const)

export function pollWhileHealthy(intervalMs: number) {
  return (query: QueryWithStatus): number | false =>
    query.state.status === 'error' ? false : intervalMs
}

export const taskRefetchInterval = pollWhileHealthy(TASK_REFETCH_MS)
export const standardRefetchInterval = pollWhileHealthy(STANDARD_REFETCH_MS)
