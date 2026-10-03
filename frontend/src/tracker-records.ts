import { currentVietnamMonth } from '@/tracker-ui'
export type RecordMode = 'recent' | 'day' | 'month' | 'quarter' | 'year'
export type RecordsSelection = { mode: RecordMode; trackerId: string; anchor: string; order: 'asc' | 'desc'; page: number; expanded: boolean }
export function initialRecordsSelection(): RecordsSelection {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date())
  const v = (k: string) => today.find(p => p.type === k)?.value
  return { mode: 'recent', trackerId: 'all', anchor: `${v('year')}-${v('month')}-${v('day')}`, order: 'desc', page: 0, expanded: false }
}
export function periodBounds(mode: RecordMode, anchor: string): { from: string; to: string } | null {
  if (mode === 'recent') return null
  if (!/^\d{4}-\d{2}-\d{2}$/.test(anchor)) return null
  const parsed = new Date(`${anchor}T00:00:00Z`)
  if (!Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== anchor || Number(anchor.slice(0,4)) < 1 || Number(anchor.slice(0,4)) > 9998) return null
  const start = new Date(parsed)
  if (mode !== 'day') start.setUTCDate(1)
  if (mode === 'quarter') start.setUTCMonth(Math.floor(start.getUTCMonth() / 3) * 3)
  if (mode === 'year') start.setUTCMonth(0)
  const end = new Date(start)
  if (mode === 'day') end.setUTCDate(end.getUTCDate() + 1)
  else end.setUTCMonth(end.getUTCMonth() + (mode === 'month' ? 1 : mode === 'quarter' ? 3 : 12))
  return { from: `${start.toISOString().slice(0,10)}T00:00:00+07:00`, to: `${end.toISOString().slice(0,10)}T00:00:00+07:00` }
}
export function recordsUrl(selection: RecordsSelection): string | null {
  const bounds = periodBounds(selection.mode, selection.anchor)
  if (selection.mode !== 'recent' && !bounds) return null
  const params = new URLSearchParams({ limit: selection.mode === 'recent' ? '20' : '51', offset: String(selection.mode === 'recent' ? 0 : selection.page * 50), order: selection.order })
  if (selection.trackerId !== 'all') params.set('tracker_id', selection.trackerId)
  if (bounds) { params.set('from', bounds.from); params.set('to', bounds.to) }
  return `/api/tracker/entries?${params}`
}
export function activityLevel(count: number): 0 | 1 | 2 | 3 { return count <= 0 ? 0 : count === 1 ? 1 : count === 2 ? 2 : 3 }
export function initialHeatmapMonth(year: number): string { const current = currentVietnamMonth(); return current.startsWith(String(year).padStart(4,'0')) ? current : `${String(year).padStart(4,'0')}-01` }
