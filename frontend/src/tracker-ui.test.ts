import { describe, expect, it } from 'vitest'

import {
  amountToNumber,
  backdateOptions,
  canSubmitAmount,
  currentVietnamMonth,
  digitsOnly,
  formatLastSeen,
  formatVnd,
  sortTrackersForGrid,
  type Tracker,
} from '@/tracker-ui'

function tracker(overrides: Partial<Tracker> = {}): Tracker {
  return {
    id: 'tracker-1',
    name: 'Hút thuốc',
    kind: 'health',
    direction: 'out',
    input_mode: 'event',
    group_id: null,
    unit: null,
    color: null,
    is_private: false,
    last_entry_at: null,
    entry_count_30d: 0,
    created_at: null,
    updated_at: null,
    ...overrides,
  }
}

describe('tracker grid order (§5.2)', () => {
  it('sorts by 30-day count, then last entry, then name for determinism', () => {
    const now = Date.now()
    const ordered = sortTrackersForGrid([
      tracker({ id: 'a', name: 'Bia', entry_count_30d: 2, last_entry_at: new Date(now - 25_000_000).toISOString() }),
      tracker({ id: 'b', name: 'Thuốc', entry_count_30d: 5, last_entry_at: new Date(now - 86_400_000).toISOString() }),
      tracker({ id: 'c', name: 'Cà phê', entry_count_30d: 2, last_entry_at: new Date(now - 17_280_000).toISOString() }),
      tracker({ id: 'd', name: 'cà phê', entry_count_30d: 2, last_entry_at: new Date(now - 17_280_000).toISOString() }),
    ])
    expect(ordered.map((item) => item.id)).toEqual(['b', 'd', 'c', 'a'])
  })

  it('does not mutate the input list', () => {
    const input = [tracker({ id: 'z' }), tracker({ id: 'a' })]
    sortTrackersForGrid(input)
    expect(input.map((item) => item.id)).toEqual(['z', 'a'])
  })
})

describe('money input rules (§5.4)', () => {
  it('strips every non-digit as the user types', () => {
    expect(digitsOnly('100.000')).toBe('100000')
    expect(digitsOnly('1.000,50')).toBe('100050')
  })

  it('formats the exact number that will be sent to the server', () => {
    expect(amountToNumber('100000')).toBe(100000)
    expect(formatVnd(amountToNumber('100000'))).toBe('100.000 ₫')
    expect(formatVnd(amountToNumber('99999999999999'))).toBe('99.999.999.999.999 ₫')
  })

  it('disables submit on empty input', () => {
    expect(canSubmitAmount('')).toBe(false)
    expect(canSubmitAmount('0')).toBe(true)
  })
})

describe('Vietnam-time helpers', () => {
  it('renders last-seen labels', () => {
    const now = new Date('2026-08-05T12:00:00Z')
    expect(formatLastSeen(null, now)).toBe('Chưa ghi')
    expect(formatLastSeen(new Date(now.getTime() - 30_000).toISOString(), now)).toBe('Vừa xong')
    expect(formatLastSeen(new Date(now.getTime() - 5 * 60_000).toISOString(), now)).toBe('5 phút trước')
    expect(formatLastSeen(new Date(now.getTime() - 3 * 3_600_000).toISOString(), now)).toBe('3 giờ trước')
    expect(formatLastSeen(new Date(now.getTime() - 4 * 86_400_000).toISOString(), now)).toBe('4 ngày trước')
  })

  it('builds backdate options with a +07:00 offset', () => {
    const options = backdateOptions(new Date('2026-08-05T12:00:00Z'))
    expect(options.map((option) => option.label)).toEqual(['Hôm qua', '2 giờ trước'])
    for (const option of options) {
      expect(option.value).toMatch(/\+07:00$/)
    }
  })

  it('formats the current month key as YYYY-MM', () => {
    expect(currentVietnamMonth(new Date('2026-08-05T12:00:00Z'))).toBe('2026-08')
  })
})
