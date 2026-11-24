import { afterEach, expect, it, vi } from 'vitest'
import { environmentManager, focusManager, QueryClient, QueryObserver } from '@tanstack/react-query'
import { HUMAN_IDLE_MS, humanActive, startHumanActivity } from '../src/human-activity'
import { taskRefetchInterval } from '../src/query-polling'
import { defaultHistoryFilters } from '../src/features/migarden/historyQuery'

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); environmentManager.setIsServer(() => typeof window === 'undefined'); focusManager.setFocused(undefined) })

it('stops visible read polling after five minutes and revalidates on genuine input', async () => {
  vi.useFakeTimers()
  environmentManager.setIsServer(() => false)
  focusManager.setFocused(true)
  const target = new EventTarget()
  vi.stubGlobal('window', target)
  vi.stubGlobal('document', { visibilityState: 'visible' })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const stop = startHumanActivity(client)
  let calls = 0
  const observer = new QueryObserver(client, { queryKey: ['tasks', 'idle-proof'], queryFn: async () => ++calls, refetchInterval: taskRefetchInterval })
  const unsub = observer.subscribe(() => undefined)
  try {
    await vi.advanceTimersByTimeAsync(HUMAN_IDLE_MS + 2_000)
    expect(humanActive()).toBe(false)
    const settled = calls
    await vi.advanceTimersByTimeAsync(350_000)
    expect(calls).toBe(settled)
    target.dispatchEvent(new Event('pointerdown'))
    await vi.advanceTimersByTimeAsync(0)
    expect(humanActive()).toBe(true)
    expect(calls).toBe(settled + 1)
    await vi.advanceTimersByTimeAsync(1_000)
    expect(calls).toBe(settled + 2)
  } finally { unsub(); stop(); client.clear() }
})

it('defaults to seven calendar days including today at the UTC+7 boundary', () => {
  expect(defaultHistoryFilters(new Date('2026-11-22T16:59:59Z'))).toMatchObject({ from_day: '2026-11-16', to_day: '2026-11-22', category: 'all' })
  expect(defaultHistoryFilters(new Date('2026-11-22T17:00:00Z'))).toMatchObject({ from_day: '2026-11-17', to_day: '2026-11-23' })
})


it('A228 retains other-feature invalidation on return while miGarden deduplicates its in-flight GET', async () => {
  vi.useFakeTimers()
  environmentManager.setIsServer(() => false)
  focusManager.setFocused(true)
  const target = new EventTarget()
  vi.stubGlobal('window', target)
  vi.stubGlobal('document', { visibilityState: 'visible' })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const stop = startHumanActivity(client)
  const signals: Record<string, AbortSignal[]> = { tasks: [], migarden: [] }
  const observers = Object.keys(signals).map(family => {
    const key = [family, 'synthetic-revalidation']
    client.setQueryData(key, 1)
    return new QueryObserver(client, { queryKey: key, queryFn: ({ signal }) => { signals[family].push(signal); return new Promise(() => undefined) } })
  })
  const unsub = observers.map(observer => observer.subscribe(() => undefined))
  try {
    await vi.advanceTimersByTimeAsync(HUMAN_IDLE_MS + 1)
    target.dispatchEvent(new Event('pointerdown'))
    await vi.advanceTimersByTimeAsync(0)
    expect(signals.tasks).toHaveLength(2)
    expect(signals.tasks[0].aborted).toBe(true)
    expect(signals.migarden).toHaveLength(1)
    expect(signals.migarden[0].aborted).toBe(false)
  } finally { for (const off of unsub) off(); stop(); client.clear() }
})
