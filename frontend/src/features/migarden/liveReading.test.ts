import { afterEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryObserver, environmentManager } from '@tanstack/react-query'
import type { GardenState } from './api'
import { acceptGardenReading, gardenDependencyChanges, invalidateGardenDependencies, gardenServerNow, patchGardenState, refreshGarden } from './liveReading'
import { displayedSession } from './presentation'

const epoch = Date.parse('2026-11-23T00:00:00Z')
const stamp = (ms = 0) => new Date(epoch + ms).toISOString()
const raw = (overrides: Partial<GardenState> = {}) => ({
  zone_id: 'synthetic-zone-a', binding_ref: 'synthetic-binding', server_time: stamp(), connection: 'fresh',
  snapshot_received_at: stamp(), last_seen_at: stamp(),
  snapshot: { output: 'off', observed_at: stamp(), time_quality: 'synced', active_session: null },
  config: {}, start_request: null, stop_request: null, next_schedule: {}, ...overrides,
}) as GardenState

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); environmentManager.setIsServer(() => typeof window === 'undefined') })

describe('A228 accepted reports and control freshness', () => {
  it.each([14_999, 15_000, 15_001])('uses the exact server receipt boundary at %i ms', age => {
    const state = acceptGardenReading(undefined, raw(), 1000)
    expect(displayedSession(state, 1000, 1000 + age, true).fresh).toBe(age < 15_000)
  })
  it('does not renew age on an unchanged server_time, even after repeated successful GETs', () => {
    let state = acceptGardenReading(undefined, raw(), 1000)
    for (const elapsed of [7000, 14_000, 15_000, 30_000]) {
      state = acceptGardenReading(state, raw(), 1000 + elapsed)
      expect(gardenServerNow(state, 1000 + elapsed, 1000 + elapsed)).toBe(epoch + elapsed)
      expect(displayedSession(state, 1000 + elapsed, 1000 + elapsed, true).fresh).toBe(elapsed < 15_000)
    }
  })
  it('rejects an older response and an older snapshot with a later GET server time', () => {
    const current = acceptGardenReading(undefined, raw({ server_time: stamp(5000), snapshot_received_at: stamp(5000), snapshot: { ...raw().snapshot!, output: 'on' } }), 6000)
    expect(acceptGardenReading(current, raw(), 7000)).toBe(current)
    const delayed = acceptGardenReading(current, raw({ server_time: stamp(6000) }), 7000)
    expect(delayed.snapshot).toEqual(current.snapshot)
    expect(delayed.snapshot_received_at).toBe(current.snapshot_received_at)
    expect(delayed.confirmedOutput).toEqual(current.confirmedOutput)
  })
  it('preserves newer config and commands even when an older projection has a later GET server time', () => {
    const state = raw({ config: { desired_saved_at: stamp(3000), applied_confirmed_at: stamp(2000) } as GardenState['config'], stop_request: { confirmed_at: stamp(3000), request_id: 'new' } as GardenState['stop_request'] })
    const current = acceptGardenReading(undefined, state, 4000)
    const incoming = raw({ server_time: stamp(5000), config: { desired_saved_at: stamp(), applied_confirmed_at: stamp() } as GardenState['config'] })
    const accepted = acceptGardenReading(current, incoming, 6000)
    expect(accepted.config).toEqual(current.config)
    expect(accepted.stop_request).toEqual(current.stop_request)
  })
  it('ages a reread of the same snapshot and renews a newer report with the same output', () => {
    const first = acceptGardenReading(undefined, raw(), 1000)
    const reread = acceptGardenReading(first, raw({ server_time: stamp(15_000) }), 16_000)
    expect(displayedSession(reread, 16_000, 16_000, true).fresh).toBe(false)
    const renewed = acceptGardenReading(reread, raw({ server_time: stamp(16_000), snapshot_received_at: stamp(16_000) }), 17_000)
    expect(displayedSession(renewed, 17_000, 17_000, true).fresh).toBe(true)
    expect(renewed.confirmedOutput).toEqual({ output: 'off', receivedAt: stamp(16_000) })
  })
  it('retains only matching snapshot confirmations through UNKNOWN; command, config and health never confirm output', () => {
    const off = acceptGardenReading(undefined, raw(), 0)
    const unknown = raw({ snapshot: { ...raw().snapshot!, output: 'unknown' }, snapshot_received_at: stamp(1000) })
    expect(acceptGardenReading(off, unknown, 1000).confirmedOutput).toEqual(off.confirmedOutput)
    expect(acceptGardenReading(off, { ...unknown, zone_id: 'other-zone' }, 1000).confirmedOutput).toBeNull()
    expect(acceptGardenReading(off, { ...unknown, binding_ref: 'new-binding' }, 1000).confirmedOutput).toBeNull()
    expect(acceptGardenReading(undefined, { ...unknown, stop_request: { status: 'processed' } as GardenState['stop_request'] }, 0).confirmedOutput).toBeNull()
    expect(acceptGardenReading(undefined, raw({ snapshot: null, snapshot_received_at: null }), 0).confirmedOutput).toBeNull()
  })
  it('stops ON extrapolation at expiry without declaring a completed session', () => {
    const state = acceptGardenReading(undefined, raw({ snapshot: { ...raw().snapshot!, output: 'on', active_session: { session_id: 's', elapsed_seconds: 7, duration_seconds: 900 } as NonNullable<GardenState['snapshot']>['active_session'] } }), 1000)
    expect(displayedSession(state, 1000, 15_999, true)).toEqual({ fresh: true, live: true, elapsed: 21 })
    expect(displayedSession(state, 1000, 16_000, true)).toEqual({ fresh: false, live: false, elapsed: 7 })
    expect(displayedSession(state, 1000, 60_000, true).elapsed).toBe(7)
  })
  it('does not invalidate dependencies for server time alone; catches same-ref evidence, health/boot and forecast changes', () => {
    const state = raw()
    expect([...gardenDependencyChanges(state, { ...state, server_time: stamp(1000) })]).toEqual([])
    expect([...gardenDependencyChanges(state, { ...state, last_seen_at: stamp(1000), snapshot_received_at: stamp(1000), snapshot: { ...state.snapshot!, observed_at: stamp(1000) } })]).toEqual([])
    expect([...gardenDependencyChanges(state, { ...state, health: { sample_id: 'new-boot' } as GardenState['health'] })]).toEqual(['health'])
    expect([...gardenDependencyChanges(state, { ...state, next_schedule: { ...state.next_schedule, next_at: stamp(1000) } })]).toEqual(['daily'])
    expect(gardenDependencyChanges(state, { ...state, config: { ...state.config, application_status: 'rejected', reason: 'storage_failure' } }).has('version')).toBe(true)
  })
  it('new same-value heartbeat receipts renew the report without refetching any active dependency', async () => {
    vi.stubGlobal('document', { visibilityState: 'visible' })
    environmentManager.setIsServer(() => false)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const families = ['history', 'daily', 'versions', 'version', 'health']
    const calls = Object.fromEntries(families.map(family => [family, 0]))
    const observers = families.map(family => new QueryObserver(client, { queryKey: ['migarden', family], queryFn: async () => ++calls[family] }))
    const subscriptions = observers.map(observer => observer.subscribe(() => undefined))
    try {
      await Promise.all(observers.map(observer => observer.refetch({ cancelRefetch: false })))
      const baseline = { ...calls }
      let previous = acceptGardenReading(undefined, raw(), 1000)
      for (const elapsed of [5000, 10_000, 16_000]) {
        const next = acceptGardenReading(previous, raw({ server_time: stamp(elapsed), snapshot_received_at: stamp(elapsed), last_seen_at: stamp(elapsed), snapshot: { ...raw().snapshot!, observed_at: stamp(elapsed) } }), 1000 + elapsed)
        invalidateGardenDependencies(client, previous, next)
        expect(displayedSession(next, 1000 + elapsed, 1000 + elapsed, true).fresh).toBe(true)
        previous = next
      }
      await new Promise(resolve => setTimeout(resolve, 0))
      expect(calls).toEqual(baseline)
    } finally { for (const off of subscriptions) off(); client.clear() }
  })
  it('cancels a delayed GET before command/config patches and keeps the snapshot clock', async () => {
    vi.useFakeTimers(); vi.setSystemTime(1000)
    environmentManager.setIsServer(() => false)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const key = ['migarden', 'state', 'session-a']
    const accepted = acceptGardenReading(undefined, raw(), 1000)
    client.setQueryData(key, accepted)
    let release!: (state: typeof accepted) => void
    let signal!: AbortSignal
    const observer = new QueryObserver(client, { queryKey: key, queryFn: ({ signal: next }) => { signal = next; return new Promise<typeof accepted>(resolve => { release = resolve }) } })
    const unsub = observer.subscribe(() => undefined)
    try {
      await vi.advanceTimersByTimeAsync(0)
      const stale = release, oldSignal = signal
      const config = { ...accepted.config, application_status: 'pending' as const }
      const command = { request_id: 'accepted-stop', status: 'pending' } as NonNullable<GardenState['stop_request']>
      await patchGardenState(client, key, { config, stop_request: command })
      expect(oldSignal.aborted).toBe(true)
      stale(accepted)
      await vi.advanceTimersByTimeAsync(0)
      const current = client.getQueryData<typeof accepted>(key)!
      expect(current.config).toEqual(config)
      expect(current.stop_request).toEqual(command)
      expect(current.readClock).toEqual(accepted.readClock)
      expect(current.snapshot_received_at).toBe(accepted.snapshot_received_at)
      expect(client.getQueryState(key)?.dataUpdatedAt).toBe(1000)
      expect(client.getQueryData(['migarden', 'state', 'session-b'])).toBeUndefined()
    } finally { unsub(); client.clear() }
  })
  it('manual refresh reads only enabled active queries in the matching session and does not cancel an in-flight read', async () => {
    vi.stubGlobal('document', { visibilityState: 'visible' })
    environmentManager.setIsServer(() => false)
    const client = new QueryClient()
    const cancel = vi.spyOn(client, 'cancelQueries')
    const active = new QueryObserver(client, { queryKey: ['migarden', 'state', 'a'], queryFn: () => new Promise(() => undefined) })
    const disabledFn = vi.fn(async () => 1)
    const disabled = new QueryObserver(client, { queryKey: ['migarden', 'history', 'a', 'hidden'], queryFn: disabledFn, enabled: false })
    const a = active.subscribe(() => undefined), b = disabled.subscribe(() => undefined)
    const refetch = vi.spyOn(client, 'refetchQueries')
    refreshGarden(client)
    expect(refetch).toHaveBeenCalledWith(expect.objectContaining({ type: 'active' }), { cancelRefetch: false })
    expect(disabledFn).not.toHaveBeenCalled()
    expect(cancel).not.toHaveBeenCalled()
    a(); b(); client.clear()
  })
})
