import { describe, expect, it } from 'vitest'
import { freshnessState, FRESH_WINDOW_MS } from '../src/freshness'

describe('active tab freshness', () => {
  const now = 100_000
  const good = { status: 'success', updatedAt: now - 1, paused: false }
  it('requires successful data from every active source', () => {
    expect(freshnessState([], now, true, true)).toBe('loading')
    expect(freshnessState([good], now, true, true)).toBe('live')
    expect(freshnessState([good, { ...good, updatedAt: 0 }], now, true, true)).toBe('loading')
    expect(freshnessState([good, { ...good, status: 'error' }], now, true, true)).toBe('error')
  })
  it('expires on the boundary and never calls offline or background data live', () => {
    expect(freshnessState([{ ...good, updatedAt: now - FRESH_WINDOW_MS }], now, true, true)).toBe('stale')
    expect(freshnessState([good], now, false, true)).toBe('offline')
    expect(freshnessState([good], now, true, false)).toBe('paused')
    expect(freshnessState([{ ...good, paused: true }], now, true, true)).toBe('paused')
  })
})
