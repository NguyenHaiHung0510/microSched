import { describe, expect, it } from 'vitest'
import { groupHeatmapEntries, heatmapDateLabel, heatmapEntryValue, heatmapGroupTotal, heatmapKindLabel } from '../src/tracker-heatmap'
import type { Entry, Tracker } from '../src/tracker-ui'

const tracker = { id: 'a', name: 'Synthetic', kind: 'general', input_mode: 'event', direction: 'out', unit: 'trang', is_private: false } as Tracker
const entry = (patch: Partial<Entry> = {}) => ({ id: 'entry', tracker_id: 'a', amount: null, quantity: null, note_md: null, occurred_at: '2026-10-13T17:15:00Z', ...patch }) as Entry

describe('heatmap grouped preview', () => {
  it('retains money, quantity and event dimensions after tracker mode changes', () => {
    const rows = [entry({ amount: 35000 }), entry({ amount: 45000 }), entry({ quantity: 2.5 }), entry({ quantity: 3 }), entry()]
    expect(heatmapGroupTotal(rows, tracker)).toBe('80.000 ₫ · 5,5 trang · 1 lần')
    expect(heatmapEntryValue(rows[0], tracker)).toBe('35.000 ₫')
    expect(heatmapEntryValue(rows[2], tracker)).toBe('2,5 trang')
    expect(heatmapEntryValue(rows[4], tracker)).toBe('1 lần')
  })
  it('does not turn zero money into an event or guess a unit', () => {
    expect(heatmapGroupTotal([entry({ amount: 0 })], tracker)).toBe('0 ₫')
    expect(heatmapEntryValue(entry({ quantity: 2 }), { ...tracker, unit: null })).toBe('2')
  })
  it('groups only current visible trackers and the selected tracker', () => {
    const privateTracker = { ...tracker, id: 'private', is_private: true }
    const other = { ...tracker, id: 'b' }
    const rows = [entry(), entry({ tracker_id: 'b' }), entry({ tracker_id: 'private' }), entry({ tracker_id: 'missing' })]
    expect(groupHeatmapEntries(rows, [tracker, other, privateTracker], 'all', false).map(group => group.tracker.id)).toEqual(['a', 'b'])
    expect(groupHeatmapEntries(rows, [tracker, other, privateTracker], 'b', true).map(group => group.tracker.id)).toEqual(['b'])
    expect(groupHeatmapEntries(rows, [tracker, other, privateTracker], 'private', false)).toEqual([])
    expect(groupHeatmapEntries(rows, [tracker, other, privateTracker], 'all', true)).toHaveLength(3)
  })
  it('uses the actual tracker kind and an explicit Vietnam calendar date', () => {
    expect(heatmapKindLabel(tracker)).toBe('Thói quen')
    expect(heatmapKindLabel({ ...tracker, input_mode: 'quantity' })).toBe('Số lượng')
    expect(heatmapKindLabel({ ...tracker, kind: 'finance', direction: 'in' })).toBe('Thu nhập')
    expect(heatmapDateLabel('2026-10-14')).toMatch(/14\/10\/2026/)
    expect(heatmapDateLabel('2024-02-29')).toMatch(/29\/02\/2024/)
  })
})
