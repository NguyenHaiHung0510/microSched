import { describe, expect, it } from 'vitest'
import { historyDay, historyIdentity, historyTime, type HistoryRow } from './reminder-history'

const row = { occurrence_ref: { origin: 'tracker_dispatch', id: 'same-id' }, occurrence_at: null,
  occurrence_on: '2026-10-23', time_basis: 'dispatch_day' } as HistoryRow

describe('durable history display', () => {
  it('keeps the origin in occurrence identity and does not invent a legacy clock', () => {
    expect(historyIdentity(row)).toBe('tracker_dispatch:same-id')
    expect(historyIdentity({ ...row, occurrence_ref: { origin: 'one_shot', id: 'same-id' } })).not.toBe(historyIdentity(row))
    expect(historyTime(row)).toBe('Không lưu giờ')
    expect(historyTime({ ...row, occurrence_on: null })).toBe('Không lưu thời điểm')
  })
  it('labels recorded-only time and groups by the supplied Vietnamese calendar day', () => {
    expect(historyTime({ ...row, occurrence_at: '2026-10-22T18:30:00Z', time_basis: 'recorded_only' })).toBe('01:30 · lúc ghi nhận')
    expect(historyDay(row.occurrence_on!)).toContain('23')
    expect(historyDay('')).toBe('Chưa rõ ngày nhắc')
  })
})
