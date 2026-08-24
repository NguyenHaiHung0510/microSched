import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, test, vi } from 'vitest'
import {
  environmentManager,
  focusManager,
  QueryClient,
  QueryObserver,
} from '@tanstack/react-query'

import { CALENDAR_QUERY_SPECS } from '../src/calendar-queries'
import {
  APP_QUERY_DEFAULTS,
  NO_POLLING_QUERY_OPTIONS,
  standardRefetchInterval,
  taskRefetchInterval,
} from '../src/query-polling'

beforeEach(() => {
  environmentManager.setIsServer(() => false)
})

afterEach(() => {
  environmentManager.setIsServer(() => typeof window === 'undefined')
  focusManager.setFocused(undefined)
  vi.useRealTimers()
})

function queryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        ...APP_QUERY_DEFAULTS,
        retry: false,
      },
    },
  })
}

async function settleInitialFetch() {
  await Promise.resolve()
  await vi.advanceTimersByTimeAsync(0)
}

test.each([
  ['task', taskRefetchInterval, 1_000],
  ['standard', standardRefetchInterval, 15_000],
] as const)('%s polling fires exactly at its cadence boundary', async (_, interval, cadence) => {
  vi.useFakeTimers()
  focusManager.setFocused(true)
  const client = queryClient()
  let calls = 0
  const observer = new QueryObserver(client, {
    queryKey: ['cadence', cadence],
    queryFn: async () => ++calls,
    refetchInterval: interval,
  })
  const unsubscribe = observer.subscribe(() => undefined)

  try {
    await settleInitialFetch()
    assert.equal(calls, 1)

    await vi.advanceTimersByTimeAsync(cadence - 1)
    assert.equal(calls, 1)

    await vi.advanceTimersByTimeAsync(1)
    assert.equal(calls, 2)

    await vi.advanceTimersByTimeAsync(cadence * 3)
    assert.equal(calls, 5)
  } finally {
    unsubscribe()
    client.clear()
  }
})

test.each([
  ['task', taskRefetchInterval],
  ['standard', standardRefetchInterval],
] as const)('%s polling stops after the query enters error', async (_, interval) => {
  vi.useFakeTimers()
  focusManager.setFocused(true)
  const client = queryClient()
  let calls = 0
  const observer = new QueryObserver(client, {
    queryKey: ['error-stop', String(interval)],
    queryFn: async () => {
      calls += 1
      if (calls === 2) throw new Error('deliberate polling failure')
      return calls
    },
    refetchInterval: interval,
  })
  const unsubscribe = observer.subscribe(() => undefined)

  try {
    await settleInitialFetch()
    const cadence = interval === taskRefetchInterval ? 1_000 : 15_000
    await vi.advanceTimersByTimeAsync(cadence)
    assert.equal(calls, 2)
    await vi.advanceTimersByTimeAsync(60_000)
    assert.equal(calls, 2)
  } finally {
    unsubscribe()
    client.clear()
  }
})

test('a query using app defaults has no interval', async () => {
  vi.useFakeTimers()
  focusManager.setFocused(true)
  const client = queryClient()
  let calls = 0
  const observer = new QueryObserver(client, {
    queryKey: ['default-no-poll'],
    queryFn: async () => ++calls,
  })
  const unsubscribe = observer.subscribe(() => undefined)

  try {
    await settleInitialFetch()
    assert.equal(calls, 1)
    await vi.advanceTimersByTimeAsync(60_000)
    assert.equal(calls, 1)
  } finally {
    unsubscribe()
    client.clear()
  }
})

test('calendar and shared no-poll options remain explicit', () => {
  assert.equal(APP_QUERY_DEFAULTS.refetchInterval, false)
  assert.equal(APP_QUERY_DEFAULTS.refetchIntervalInBackground, false)
  assert.equal(APP_QUERY_DEFAULTS.refetchOnMount, true)
  assert.equal(APP_QUERY_DEFAULTS.refetchOnWindowFocus, true)
  assert.equal(NO_POLLING_QUERY_OPTIONS.refetchInterval, false)
  for (const spec of CALENDAR_QUERY_SPECS) {
    assert.equal(spec.refetchInterval, false, `${String(spec.queryKey)} must not poll`)
  }
})

test('App and ReminderConfirm wire the explicit no-poll session policy', () => {
  for (const filename of ['App.tsx', 'ReminderConfirmScreen.tsx']) {
    const source = readFileSync(new URL(`../src/${filename}`, import.meta.url), 'utf8')
    const spreads = source.match(/\.\.\.NO_POLLING_QUERY_OPTIONS/g) ?? []
    assert.equal(spreads.length, 1, `${filename} must explicitly spread no-poll options`)
  }
})

test('hidden pauses intervals; one focus wave fetches once per unique query key', async () => {
  vi.useFakeTimers()
  focusManager.setFocused(true)
  const client = queryClient()
  client.mount()
  let calls = 0
  const options = {
    queryKey: ['shared-session'],
    queryFn: async () => ++calls,
    refetchInterval: taskRefetchInterval,
    staleTime: 0,
  }
  const first = new QueryObserver(client, options)
  const second = new QueryObserver(client, options)
  const unsubscribeFirst = first.subscribe(() => undefined)
  const unsubscribeSecond = second.subscribe(() => undefined)

  try {
    await settleInitialFetch()
    assert.equal(calls, 1, 'two observers must share the initial network fetch')

    focusManager.setFocused(false)
    await vi.advanceTimersByTimeAsync(5_000)
    assert.equal(calls, 1, 'hidden/inactive queries must not poll')

    focusManager.setFocused(true)
    await settleInitialFetch()
    assert.equal(calls, 2, 'focus must fetch once for the unique query key')
  } finally {
    unsubscribeSecond()
    unsubscribeFirst()
    client.unmount()
    client.clear()
  }
})

test('unsubscribing the last observer stops its interval', async () => {
  vi.useFakeTimers()
  focusManager.setFocused(true)
  const client = queryClient()
  let calls = 0
  const observer = new QueryObserver(client, {
    queryKey: ['unmount-stop'],
    queryFn: async () => ++calls,
    refetchInterval: taskRefetchInterval,
  })
  const unsubscribe = observer.subscribe(() => undefined)

  await settleInitialFetch()
  assert.equal(calls, 1)
  unsubscribe()
  await vi.advanceTimersByTimeAsync(60_000)
  assert.equal(calls, 1)
  client.clear()
})
