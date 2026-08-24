import assert from 'node:assert/strict'
import { test, vi } from 'vitest'
import { QueryClient, QueryObserver } from '@tanstack/react-query'

import { CALENDAR_QUERY_SPECS } from '../src/calendar-queries'

/**
 * 010b §2 mục 8 (CRITICAL) / 021: polling is opt-in app-wide, and every Calendar
 * query still carries an explicit `refetchInterval: false`. The grid mounts 13
 * month queries plus annotations, tasks and sources, then grows while scrolling;
 * this regression net keeps that fanout outside every interval policy.
 */
test('every 010b query spec explicitly opts out of the live polling default', () => {
  assert.ok(CALENDAR_QUERY_SPECS.length >= 5)
  for (const spec of CALENDAR_QUERY_SPECS) {
    assert.equal(spec.refetchInterval, false, `${String(spec.queryKey)} must opt out`)
  }
})

test('calendar specs override even a caller that supplies a polling default', async () => {
  vi.useFakeTimers()
  try {
    const client = new QueryClient({
      defaultOptions: {
        queries: {
          // A hostile/caller-supplied default must not override Calendar.
          refetchInterval: (query) => (query.state.status === 'error' ? false : 1000),
        },
      },
    })
    const calls: string[] = []
    const observers = CALENDAR_QUERY_SPECS.map(
      (spec) =>
        new QueryObserver(client, {
          ...spec,
          queryFn: async () => {
            calls.push(String(spec.queryKey.join(':')))
            return { items: [] }
          },
        }),
    )
    const unsubscribes = observers.map((observer) => observer.subscribe(() => undefined))

    // Let the initial fetches settle, then wait three full polling windows.
    await Promise.resolve()
    await Promise.resolve()
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(3_000)
    unsubscribes.forEach((unsubscribe) => unsubscribe())

    // Exactly one call per spec: the interval must never have fired.
    assert.equal(calls.length, CALENDAR_QUERY_SPECS.length)
    for (const spec of CALENDAR_QUERY_SPECS) {
      const key = String(spec.queryKey.join(':'))
      assert.equal(calls.filter((call) => call === key).length, 1, `${key} refetched`)
    }
  } finally {
    vi.useRealTimers()
  }
})
