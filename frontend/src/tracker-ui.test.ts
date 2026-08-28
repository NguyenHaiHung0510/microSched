import { describe, expect, it } from 'vitest'

import {
  amountToNumber,
  backdateOptions,
  buildTrackerWritePayload,
  canSubmitAmount,
  capturePayload,
  currentVietnamMonth,
  decimalInput,
  digitsOnly,
  formatLastSeen,
  formatQuantity,
  formatReminderSchedule,
  formatReminderSummary,
  formatVnd,
  groupRemindersByHour,
  groupTrackersByGroup,
  quantityToNumber,
  quietAgo,
  sortTrackersForGrid,
  trackerKindLabel,
  type Tracker,
  type TrackerGroup,
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
    reminder_time: null,
    reminder_text: null,
    reminder_mode: null,
    reminder_interval_days: null,
    reminder_action: null,
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

  it('groups trackers by group ID and isolates unassigned trackers', () => {
    const groups: TrackerGroup[] = [
      { id: 'g1', name: 'Thuốc sáng', kind: 'health', color: null, position: 0, tracker_count: 2, created_at: null, updated_at: null },
      { id: 'g2', name: 'Chi tiêu', kind: 'finance', color: null, position: 1, tracker_count: 0, created_at: null, updated_at: null },
    ]
    const trackers: Tracker[] = [
      tracker({ id: 't1', name: 'Thuốc A', group_id: 'g1' }),
      tracker({ id: 't2', name: 'Thuốc B', group_id: 'g1' }),
      tracker({ id: 't3', name: 'Hút thuốc', group_id: null }),
    ]

    const result = groupTrackersByGroup(trackers, groups)
    expect(result.grouped.length).toBe(2)
    expect(result.grouped[0].group.name).toBe('Thuốc sáng')
    expect(result.grouped[0].trackers.map((t) => t.id)).toEqual(['t1', 't2'])
    expect(result.grouped[1].group.name).toBe('Chi tiêu')
    expect(result.grouped[1].trackers.length).toBe(0)
    expect(result.unassigned.map((t) => t.id)).toEqual(['t3'])
  })

  it('clusters health reminders by scheduled time for batch preview', () => {
    const trackers: Tracker[] = [
      tracker({ id: 't1', name: 'Thuốc dạ dày', reminder_time: '08:00', reminder_text: 'Uống trước ăn' }),
      tracker({ id: 't2', name: 'Vitamin C', reminder_time: '08:00', reminder_text: null }),
      tracker({ id: 't3', name: 'Thuốc bổ mắt', reminder_time: '20:00', reminder_text: null }),
      tracker({ id: 't4', name: 'Không hẹn giờ', reminder_time: null }),
    ]

    const reminderGroups = groupRemindersByHour(trackers)
    expect(reminderGroups.length).toBe(2)
    expect(reminderGroups[0].time).toBe('08:00')
    expect(reminderGroups[0].trackers.map((t) => t.id)).toEqual(['t1', 't2'])
    expect(reminderGroups[0].previewText).toBe('Uống trước ăn')
    expect(reminderGroups[1].time).toBe('20:00')
    expect(reminderGroups[1].previewText).toBe('Nhắc nhở: Thuốc bổ mắt')
  })
})

describe('tracker kind & reminder helpers', () => {
  it('maps tracker kinds to accurate Vietnamese labels', () => {
    expect(trackerKindLabel('health')).toBe('Sức khoẻ')
    expect(trackerKindLabel('finance')).toBe('Tài chính')
    expect(trackerKindLabel('general')).toBe('Chung')
  })

  it('formats reminder schedules for fixed and after_entry modes', () => {
    expect(
      formatReminderSchedule({
        reminder_mode: 'fixed',
        reminder_interval_days: 1,
        reminder_time: '08:00',
      }),
    ).toBe('Mỗi 1 ngày lúc 08:00')

    expect(
      formatReminderSchedule({
        reminder_mode: 'fixed',
        reminder_interval_days: 3,
        reminder_time: '09:00',
      }),
    ).toBe('Mỗi 3 ngày lúc 09:00')

    expect(
      formatReminderSchedule({
        reminder_mode: 'after_entry',
        reminder_interval_days: 3,
        reminder_time: '20:30',
      }),
    ).toBe('Sau 3 ngày chưa ghi lúc 20:30')

    expect(
      formatReminderSchedule({
        reminder_mode: null,
        reminder_interval_days: null,
        reminder_time: null,
      }),
    ).toBeNull()
  })

  it('formats reminder summary badges with mode, interval, time, and action', () => {
    expect(
      formatReminderSummary({
        reminder_mode: 'fixed',
        reminder_interval_days: 3,
        reminder_time: '09:00',
        reminder_action: 'open_tracker',
      }),
    ).toBe('Mỗi 3 ngày · 09:00 · Mở tracker')

    expect(
      formatReminderSummary({
        reminder_mode: 'after_entry',
        reminder_interval_days: 3,
        reminder_time: '09:00',
        reminder_action: 'confirm_event',
      }),
    ).toBe('Sau 3 ngày chưa ghi · 09:00 · Xác nhận một chạm')

    expect(
      formatReminderSummary({
        reminder_mode: null,
        reminder_interval_days: null,
        reminder_time: null,
        reminder_action: null,
      }),
    ).toBeNull()
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

  it('keeps one decimal separator for quantity input', () => {
    expect(decimalInput('2,5')).toBe('2.5')
    expect(decimalInput('2.5')).toBe('2.5')
    expect(decimalInput('2,55')).toBe('2.55')
    expect(decimalInput('12,5,5')).toBe('12.55')
    expect(decimalInput('abc2.5')).toBe('2.5')
    expect(decimalInput('')).toBe('')
    expect(quantityToNumber('2,5')).toBe(2.5)
    expect(formatQuantity(2.5)).toBe('2,5')
    expect(formatQuantity(2)).toBe('2')
  })

  it('sends a parsed quantity number, not a stripped digit string', () => {
    const qtyTracker = tracker({ id: 'qty-1', name: 'Nước', input_mode: 'quantity', unit: 'lon' })
    expect(capturePayload(qtyTracker, '2,5').quantity).toBe(2.5)
    expect(capturePayload(qtyTracker, '2.5').quantity).toBe(2.5)
    expect(capturePayload(qtyTracker, '').quantity).toBeUndefined()
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
    // A1 stays relative beyond a week ("12 ngày trước", spec §5.1 / M6).
    expect(formatLastSeen(new Date(now.getTime() - 12 * 86_400_000).toISOString(), now)).toBe(
      '12 ngày trước',
    )
    expect(formatLastSeen(new Date(now.getTime() - 200 * 86_400_000).toISOString(), now)).toBe(
      '200 ngày trước',
    )
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

describe('tracker write payload builder and legacy reminder_text preservation', () => {
  it('sends reminder_text: null on create tracker', () => {
    const payload = buildTrackerWritePayload({
      name: 'Uống thuốc',
      kind: 'health',
      direction: 'out',
      input_mode: 'event',
      group_id: null,
      unit: null,
      is_private: false,
      reminder_enabled: true,
      reminder_mode: 'fixed',
      reminder_interval_days: 1,
      reminder_action: 'confirm_event',
      reminder_time: '08:00',
      is_edit: false,
    })
    expect(payload.reminder_text).toBeNull()
    expect('reminder_text' in payload).toBe(true)
  })

  it('omits reminder_text key on edit tracker with reminder enabled to preserve legacy text', () => {
    const payload = buildTrackerWritePayload({
      name: 'Uống thuốc (đã sửa)',
      kind: 'health',
      direction: 'out',
      input_mode: 'event',
      group_id: null,
      unit: null,
      is_private: false,
      reminder_enabled: true,
      reminder_mode: 'fixed',
      reminder_interval_days: 2,
      reminder_action: 'confirm_event',
      reminder_time: '09:00',
      is_edit: true,
    })
    expect('reminder_text' in payload).toBe(false)
    expect(payload.reminder_time).toBe('09:00')
  })

  it('sends reminder_text: null and null reminder fields when reminder is disabled on edit', () => {
    const payload = buildTrackerWritePayload({
      name: 'Uống thuốc',
      kind: 'health',
      direction: 'out',
      input_mode: 'event',
      group_id: null,
      unit: null,
      is_private: false,
      reminder_enabled: false,
      reminder_mode: 'fixed',
      reminder_interval_days: 1,
      reminder_action: 'confirm_event',
      reminder_time: '08:00',
      is_edit: true,
    })
    expect(payload.reminder_text).toBeNull()
    expect(payload.reminder_time).toBeNull()
    expect(payload.reminder_mode).toBeNull()
    expect(payload.reminder_interval_days).toBeNull()
    expect(payload.reminder_action).toBeNull()
    expect(payload.ensure_push).toBe(false)
  })
})

describe('quietAgo', () => {
  it('returns "less than 1m ago" for null', () => expect(quietAgo(null)).toBe('less than 1m ago'))
  it('returns "less than 1m ago" for < 60s', () => expect(quietAgo(59_999)).toBe('less than 1m ago'))
  it('returns "1m ago" for exactly 60s', () => expect(quietAgo(60_000)).toBe('1m ago'))
  it('returns "59m ago" for 59 min', () => expect(quietAgo(59 * 60_000)).toBe('59m ago'))
  it('returns "1h ago" for 60 min', () => expect(quietAgo(60 * 60_000)).toBe('1h ago'))
  it('returns "1d ago" for 24h', () => expect(quietAgo(24 * 60 * 60_000)).toBe('1d ago'))
  it('returns "1mo ago" for 30d', () => expect(quietAgo(30 * 24 * 60 * 60_000)).toBe('1mo ago'))
  it('returns "1y ago" for 12mo', () => expect(quietAgo(12 * 30 * 24 * 60 * 60_000)).toBe('1y ago'))
})
