import { describe, expect, it } from 'vitest'

import {
  addVietnamDays,
  allDayVietnamRange,
  eventDialogErrorMessage,
  groupEvents,
  rangeQuery,
  sourceColorToken,
  vietnamInputToIso,
} from '@/calendar-ui'

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
    expect(eventDialogErrorMessage(null, { detail: { message: 'Không lưu được.' } })).toBe('Không lưu được.')
    expect(eventDialogErrorMessage('Lỗi trong form.', new Error('ignored'))).toBe('Lỗi trong form.')
  })

  it('falls back to slate for an unknown or missing source color', () => {
    expect(sourceColorToken(null)).toBe('var(--n-500)')
    expect(sourceColorToken('unknown')).toBe('var(--n-500)')
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
})
