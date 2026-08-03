import assert from 'node:assert/strict'
import { test, vi } from 'vitest'
import { QueryClient, QueryObserver } from '@tanstack/react-query'

import { CALENDAR_QUERY_SPECS } from '../src/calendar-queries'

/**
 * 010b §2 mục 8 (CRITICAL) / §7.3: the app-wide QueryClient in main.tsx polls
 * every visible query each second. Every 010b query must carry an explicit
 * `refetchInterval: false` — the grid mounts 13 month queries plus annotations,
 * tasks and sources, so a dropped flag would become tens of requests per second
 * on Fly/Neon. This is the regression net that catches the flag going missing.
 */
test('every 010b query spec explicitly opts out of the live polling default', () => {
  assert.ok(CALENDAR_QUERY_SPECS.length >= 5)
  for (const spec of CALENDAR_QUERY_SPECS) {
    assert.equal(spec.refetchInterval, false, `${String(spec.queryKey)} must opt out`)
  }
})

test('advancing 3s with the app-wide polling default refetches nothing', async () => {
  vi.useFakeTimers()
  try {
    const client = new QueryClient({
      defaultOptions: {
        queries: {
          // Mirror main.tsx: a healthy query polls every second.
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
