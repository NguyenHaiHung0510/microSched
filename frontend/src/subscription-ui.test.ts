import { describe, expect, it } from 'vitest'

import {
  addPeriod,
  daysLeftLabel,
  periodLabel,
  renewSummary,
  statusLabel,
  subscriptionTrackers,
} from './subscription-ui'
import type { Tracker } from './tracker-ui'

describe('addPeriod (mirrors backend §4.2)', () => {
  it('adds days and weeks with plain arithmetic', () => {
    expect(addPeriod('2026-01-31', 1, 'day', 31)).toBe('2026-02-01')
    expect(addPeriod('2026-01-15', 2, 'week', 15)).toBe('2026-01-29')
  })

  it('clamps month-end to the anchor day', () => {
    expect(addPeriod('2026-01-31', 1, 'month', 31)).toBe('2026-02-28')
    expect(addPeriod('2028-01-31', 1, 'month', 31)).toBe('2028-02-29')
    expect(addPeriod('2026-12-31', 1, 'year', 31)).toBe('2027-12-31')
  })

  it('chains without drifting the payment day', () => {
    const first = addPeriod('2026-01-31', 1, 'month', 31)
    const second = addPeriod(first, 1, 'month', 31)
    const third = addPeriod(second, 1, 'month', 31)
    expect([first, second, third]).toEqual(['2026-02-28', '2026-03-31', '2026-04-30'])
  })
})

describe('labels', () => {
  it('formats period and status labels in Vietnamese', () => {
    expect(periodLabel(1, 'month')).toBe('1 tháng')
    expect(periodLabel(3, 'week')).toBe('3 tuần')
    expect(statusLabel('active')).toBe('Đang hoạt động')
    expect(statusLabel('canceled')).toBe('Đã huỷ')
    expect(statusLabel('expired')).toBe('Hết hạn')
  })

  it('keeps negative days_left readable', () => {
    expect(daysLeftLabel(-400)).toBe('Trễ 400 ngày')
    expect(daysLeftLabel(0)).toBe('Hết hạn hôm nay')
    expect(daysLeftLabel(2)).toBe('Còn 2 ngày')
  })
})

describe('renew summary', () => {
  it('shows the formatted amount and the new expiry before confirm', () => {
    expect(renewSummary('Sub AI', 260000, '2026-09-15')).toContain('260.000 ₫')
    expect(renewSummary('Sub AI', 260000, '2026-09-15')).toContain('15/09/2026')
  })
})

describe('subscriptionTrackers', () => {
  it('only allows finance + money trackers as parents (§2.5)', () => {
    const trackers = [
      { id: 'a', kind: 'finance', input_mode: 'money' },
      { id: 'b', kind: 'finance', input_mode: 'event' },
      { id: 'c', kind: 'health', input_mode: 'money' },
      { id: 'd', kind: 'health', input_mode: 'event' },
    ] as Tracker[]
    expect(subscriptionTrackers(trackers).map((tracker) => tracker.id)).toEqual(['a'])
  })
})
