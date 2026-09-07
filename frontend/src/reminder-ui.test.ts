import { describe, expect, it } from 'vitest'
import { reminderPreview, vnInput, type ReminderSourceInfo } from '@/reminder-ui'

const source: ReminderSourceInfo = { title: 'Synthetic', is_private: false, open: true,
  anchor_at: '2030-01-02T03:00:00Z', anchor_day: null, date_only: false }
describe('one-shot time preview', () => {
  it('allows custom time independently of deadline', () => {
    expect(reminderPreview({ ...source, anchor_at: null }, 'absolute', '2030-01-02T20:00', '', '', '', ''))
      .toBe('2030-01-02T13:00:00.000Z')
  })
  it.each([['15', '1', '-1', '2030-01-02T02:45:00.000Z'],
    ['2', '60', '1', '2030-01-02T05:00:00.000Z'],
    ['1', '1440', '-1', '2030-01-01T03:00:00.000Z']])('resolves before and after %s %s %s', (amount, unit, direction, result) => {
    expect(reminderPreview(source, 'relative', '', amount, unit, direction, '')).toBe(result)
  })
  it('requires explicit time for date-only sources', () => {
    const day = { ...source, anchor_at: null, anchor_day: '2030-01-02', date_only: true }
    expect(reminderPreview(day, 'relative', '', '60', '1', '-1', '')).toBeNull()
    expect(reminderPreview(day, 'relative', '', '60', '1', '-1', '09:00')).toBe('2030-01-02T01:00:00.000Z')
  })
  it('rejects negative magnitudes, fractional minutes and excessive offsets', () => {
    for (const n of ['-1', '0.5', '525601', '']) expect(reminderPreview(source, 'relative', '', n, '1', '-1', '')).toBeNull()
  })
  it('formats input in Vietnam regardless of the browser zone', () => {
    expect(vnInput('2030-01-01T18:30:00Z')).toBe('2030-01-02T01:30')
  })
})
