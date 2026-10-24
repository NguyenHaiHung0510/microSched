import { afterEach, describe, expect, it, vi } from 'vitest'
import { shiftedAnnotation, shiftedTaskSchedule, taskSchedule, validMoveDay } from './calendar-move'

vi.mock('@/outbox/core', () => ({ barrier: vi.fn(), getSnapshot: vi.fn(), subscribe: vi.fn(), unlocked: vi.fn() }))
vi.mock('@/outbox/adapters', () => ({ taskRequest: vi.fn() }))
vi.mock('@/api', () => ({ apiRequest: vi.fn() }))
afterEach(() => vi.restoreAllMocks())

describe('calendar move temporal shape', () => {
  it('keeps date-only shape and the full previous snapshot for undo', () => {
    const before = { due_precision: 'date' as const, due_on: '2026-10-26', due_at: null }
    expect(shiftedTaskSchedule(before, '2026-11-01')).toEqual({ ...before, due_on: '2026-11-01' })
    expect(taskSchedule(before)).toEqual(before)
  })
  it('shifts the VN day and preserves clock including seconds and milliseconds', () => {
    const before = { due_precision: 'datetime' as const, due_on: null, due_at: '2026-10-26T23:30:45.123+07:00' }
    const after = shiftedTaskSchedule(before, '2026-11-01')
    expect(after.due_precision).toBe('datetime')
    expect(after.due_on).toBeNull()
    expect(Date.parse(after.due_at!)).toBe(Date.parse('2026-11-01T23:30:45.123+07:00'))
    expect(taskSchedule(before).due_at).toBe(before.due_at)
  })
  it('moves a middle-grabbed range across a month without changing inclusive duration', () => {
    expect(shiftedAnnotation({ starts_on: '2026-10-26', ends_on: '2026-10-28' }, '2026-10-27', '2026-10-31'))
      .toEqual({ starts_on: '2026-10-30', ends_on: '2026-11-01' })
    expect(shiftedAnnotation({ starts_on: '2026-10-26', ends_on: '2026-10-26' }, '2026-10-26', '2026-11-01'))
      .toEqual({ starts_on: '2026-11-01', ends_on: '2026-11-01' })
  })
  it('rejects malformed dates and grabs outside the range before mutation', () => {
    expect(validMoveDay('2026-02-30')).toBe(false)
    expect(validMoveDay('')).toBe(false)
    expect(() => shiftedTaskSchedule({ due_precision: 'none', due_on: null, due_at: null }, '')).toThrow()
    expect(() => shiftedAnnotation({ starts_on: '2026-10-26', ends_on: '2026-10-28' }, '2026-10-29', '2026-11-01')).toThrow()
  })
})
