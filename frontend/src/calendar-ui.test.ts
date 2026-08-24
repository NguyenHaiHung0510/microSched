import { describe, expect, it } from 'vitest'

import { ApiError } from '@/api'
import {
  addVietnamDays,
  allDayVietnamRange,
  eventDialogErrorMessage,
  groupEvents,
  rangeQuery,
  SOURCE_COLOR_KEYS,
  SOURCE_COLOR_LABELS,
  SOURCE_COLORS,
  sourceColorToken,
  vietnamInputToIso,
} from '@/calendar-ui'
import {
  CHIP_LIMIT_DESKTOP,
  CHIP_LIMIT_MOBILE,
  mergeDayChips,
  monthKey,
  monthWeeks,
} from '@/calendar-scroll'

describe('calendar UI helpers', () => {
  it('moves the fixed Vietnam range by exactly thirty days', () => {
    expect(addVietnamDays('2026-08-01', 30)).toBe('2026-08-31')
    expect(rangeQuery('2026-08-01')).toEqual({
      from: '2026-08-01T00:00:00+07:00',
      to: '2026-08-31T00:00:00+07:00',
    })
  })

  it('always writes datetime-local values with the product offset', () => {
    expect(vietnamInputToIso('2026-08-15T08:00')).toBe('2026-08-15T08:00:00+07:00')
    expect(vietnamInputToIso('2026-08-15T08:00:12')).toBe('2026-08-15T08:00:12+07:00')
  })

  it('normalizes an all-day event to Vietnam midnight boundaries', () => {
    expect(allDayVietnamRange('2026-08-15')).toEqual({
      startsAt: '2026-08-15T00:00',
      endsAt: '2026-08-16T00:00',
    })
  })

  it('keeps event mutation errors available for the open dialog', () => {
    expect(
      eventDialogErrorMessage(
        null,
        new ApiError(422, 'Không lưu được.', { detail: { message: 'Không lưu được.' } }),
      ),
    ).toBe('Không lưu được.')
    expect(eventDialogErrorMessage('Lỗi trong form.', new Error('ignored'))).toBe('Lỗi trong form.')
  })

  it('falls back to slate for an unknown or missing source color', () => {
    expect(sourceColorToken(null)).toBe('var(--n-500)')
    expect(sourceColorToken('unknown')).toBe('var(--n-500)')
  })

  it('provides expanded curated color palette with labels', () => {
    expect(SOURCE_COLOR_KEYS).toContain('teal')
    expect(SOURCE_COLOR_KEYS).toContain('indigo')
    expect(SOURCE_COLOR_KEYS).toContain('orange')
    expect(SOURCE_COLOR_KEYS).toContain('cyan')
    expect(SOURCE_COLORS.teal).toBe('#0d9488')
    expect(SOURCE_COLOR_LABELS.teal).toBe('Xanh mòng két')
    expect(sourceColorToken('teal')).toBe('#0d9488')
  })

  it('groups event cards by their Vietnam calendar day', () => {
    const event = (id: string, starts_at: string) => ({
      id,
      source_id: 'source',
      title: id,
      starts_at,
      ends_at: starts_at,
      all_day: false,
      location: null,
      description_md: null,
      created_at: null,
      updated_at: null,
    })
    const groups = groupEvents([
      event('late', '2026-08-15T17:00:00+07:00'),
      event('next', '2026-08-16T00:00:00+07:00'),
    ])
    expect(groups.map(([day]) => day)).toEqual(['2026-08-15', '2026-08-16'])
  })

  it('isolates month days and identifies cross-month boundary days correctly', () => {
    const weeks = monthWeeks(2026, 8)
    const currentMonth = monthKey(2026, 8)
    expect(currentMonth).toBe('2026-08')
    expect(weeks.length).toBeGreaterThanOrEqual(4)

    // All days in August belong to 2026-08
    const augDays = weeks.flatMap((w) => w.days).filter((d) => d.slice(0, 7) === currentMonth)
    expect(augDays.length).toBe(31)
    expect(augDays[0]).toBe('2026-08-01')
    expect(augDays[augDays.length - 1]).toBe('2026-08-31')
  })

  it('respects desktop and mobile chip limits in mergeDayChips', () => {
    const events = [
      {
        id: 'e1',
        source_id: 's',
        title: 'Event 1',
        starts_at: '2026-08-15T08:00:00+07:00',
        ends_at: '2026-08-15T09:00:00+07:00',
        all_day: false,
        location: null,
        description_md: null,
        created_at: null,
        updated_at: null,
      },
      {
        id: 'e2',
        source_id: 's',
        title: 'Event 2',
        starts_at: '2026-08-15T10:00:00+07:00',
        ends_at: '2026-08-15T11:00:00+07:00',
        all_day: false,
        location: null,
        description_md: null,
        created_at: null,
        updated_at: null,
      },
    ]
    const tasks = [
      {
        id: 't1',
        title: 'Task 1',
        status: 'open' as const,
        due_precision: 'date' as const,
        due_on: '2026-08-15',
        due_at: null,
        created_at: null,
      },
      {
        id: 't2',
        title: 'Task 2',
        status: 'completed' as const,
        due_precision: 'date' as const,
        due_on: '2026-08-15',
        due_at: null,
        created_at: null,
      },
      {
        id: 't3',
        title: 'Task 3',
        status: 'open' as const,
        due_precision: 'date' as const,
        due_on: '2026-08-15',
        due_at: null,
        created_at: null,
      },
    ]

    const mobileResult = mergeDayChips(events, tasks, CHIP_LIMIT_MOBILE)
    expect(mobileResult.chips.length).toBe(2)
    expect(mobileResult.overflow).toBe(3)

    const desktopResult = mergeDayChips(events, tasks, CHIP_LIMIT_DESKTOP)
    expect(desktopResult.chips.length).toBe(4)
    expect(desktopResult.overflow).toBe(1)
  })
})
