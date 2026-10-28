import { formatQuantity, formatVnd, type Entry, type Tracker } from './tracker-ui'

export function heatmapKindLabel(tracker: Tracker): string {
  if (tracker.kind === 'finance') return tracker.direction === 'in' ? 'Thu nhập' : 'Chi tiêu'
  if (tracker.kind === 'health') return 'Sức khỏe'
  return tracker.input_mode === 'quantity' ? 'Số lượng' : 'Thói quen'
}

export function heatmapEntryValue(entry: Entry, tracker: Tracker): string {
  if (entry.amount != null) return formatVnd(entry.amount)
  if (entry.quantity != null) return `${formatQuantity(entry.quantity)}${tracker.unit ? ` ${tracker.unit}` : ''}`
  return '1 lần'
}

/** Keep historical money/quantity/event dimensions separate, even after a mode change. */
export function heatmapGroupTotal(entries: Entry[], tracker: Tracker): string {
  const money = entries.filter(entry => entry.amount != null)
  const quantities = entries.filter(entry => entry.amount == null && entry.quantity != null)
  const events = entries.length - money.length - quantities.length
  return [
    money.length ? formatVnd(money.reduce((sum, entry) => sum + entry.amount!, 0)) : null,
    quantities.length ? `${formatQuantity(quantities.reduce((sum, entry) => sum + entry.quantity!, 0))}${tracker.unit ? ` ${tracker.unit}` : ''}` : null,
    events ? `${events} lần` : null,
  ].filter(Boolean).join(' · ')
}

export function groupHeatmapEntries(entries: Entry[], trackers: Tracker[], trackerId: string, privateUnlocked: boolean) {
  return trackers.filter(tracker => (privateUnlocked || !tracker.is_private) && (trackerId === 'all' || tracker.id === trackerId))
    .map(tracker => ({ tracker, entries: entries.filter(entry => entry.tracker_id === tracker.id) }))
    .filter(group => group.entries.length > 0)
}

export function heatmapDateLabel(day: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: 'Asia/Ho_Chi_Minh', weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric',
  }).format(new Date(`${day}T00:00:00+07:00`))
}
