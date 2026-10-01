import { describe, expect, it, vi } from 'vitest'

import { domainReadOptions, isAffectedQueryKey, isWebLocksCapabilityMissing, subscribeOutboxBroadcast } from '@/lib/use-domain-outbox'

describe('outbox-aware domain reads', () => {
  it('matches affected prefixes in both global and domain query families', () => {
    expect(isAffectedQueryKey(['tasks'], ['tasks'])).toBe(true)
    expect(isAffectedQueryKey(['tasks'], ['tasks', 'timeline', '2026-10-01'])).toBe(true)
    expect(isAffectedQueryKey(['calendar', 'tasks'], ['calendar'])).toBe(false)
    expect(isAffectedQueryKey(['calendar', 'tasks'], [])).toBe(true)
    expect(isAffectedQueryKey('unknown', ['tasks'])).toBe(false)
  })

  it('blocks mount, focus, and polling while preserving standard rates when clear', () => {
    expect(domainReadOptions(true, 30_000)).toEqual({
      refetchOnMount: false,
      refetchOnReconnect: false,
      refetchOnWindowFocus: false,
      refetchInterval: false,
    })
    expect(domainReadOptions(false, 30_000)).toEqual({
      refetchOnMount: true,
      refetchOnReconnect: false,
      refetchOnWindowFocus: true,
      refetchInterval: 30_000,
    })
  })

  it('shows the coordination fallback warning before the one-shot capability event can be observed', () => {
    expect(isWebLocksCapabilityMissing(false, true)).toBe(true)
    expect(isWebLocksCapabilityMissing(true, false)).toBe(true)
    expect(isWebLocksCapabilityMissing(true, true)).toBe(false)
  })

  it('refreshes from payload-free cross-tab changed notices and closes its channel', () => {
    let listener: ((event: MessageEvent<unknown>) => void) | null = null
    const close = vi.fn()
    const constructor = vi.fn(function (this: { onmessage: typeof listener; close: typeof close }, name: string) {
      expect(name).toBe('microsched-outbox-events')
      Object.defineProperty(this, 'onmessage', { get: () => listener, set: (next) => { listener = next } })
      this.close = close
    })
    vi.stubGlobal('BroadcastChannel', constructor)
    const changed = vi.fn()
    const unsubscribe = subscribeOutboxBroadcast(changed)
    listener?.({ data: { row: 'private payload' } } as MessageEvent<unknown>)
    expect(changed).not.toHaveBeenCalled()
    listener?.({ data: 'changed' } as MessageEvent<unknown>)
    expect(changed).toHaveBeenCalledOnce()
    unsubscribe()
    expect(close).toHaveBeenCalledOnce()
    vi.unstubAllGlobals()
  })
})
