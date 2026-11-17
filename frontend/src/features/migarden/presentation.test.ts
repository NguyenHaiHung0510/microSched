import { describe, expect, it } from 'vitest'
import type { GardenState } from './api'
import { displayedSession, fromLocal, localInput } from './presentation'

describe('N01 display boundaries', () => {
  it('round-trips civil Hanoi input independent of browser timezone', () => {
    expect(fromLocal('2026-11-18T07:00')).toBe('2026-11-18T00:00:00.000Z')
    expect(localInput('2026-11-18T00:00:00.000Z')).toBe('2026-11-18T07:00')
    expect(() => fromLocal('2026-02-30T07:00')).toThrow()
  })

  it('advances only from a fresh active observation and never turns elapsed into completion', () => {
    const state = {
      snapshot_received_at: '2026-11-18T00:00:05Z',
      server_time: '2026-11-18T00:00:06Z',
      connection: 'fresh',
      snapshot: {
        observed_at: '2026-11-18T00:00:04Z', time_quality: 'synced', output: 'on',
        active_session: { elapsed_seconds: 7, duration_seconds: 15 },
      },
    } as GardenState
    expect(displayedSession(state, 1_000, 3_000, true)).toEqual({ fresh: true, live: true, elapsed: 11 })
    expect(displayedSession(state, 1_000, 20_000, true)).toEqual({ fresh: true, live: true, elapsed: 15 })
    expect(displayedSession(state, 1_000, 47_000, true)).toEqual({ fresh: false, live: false, elapsed: 7 })
    expect(displayedSession(state, 1_000, 3_000, false)).toEqual({ fresh: false, live: false, elapsed: 7 })
  })
})
