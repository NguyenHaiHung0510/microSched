import { useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { activityCountByTrackerDay, daysInReportMonth, isFutureActivityDay, reportMonthOffset } from '@/tracker-rhythm'
import type { DashboardResponse, Tracker } from '@/tracker-ui'

const WEEKDAYS = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN']

function vietnamDate(day: string): string {
  const [year, month, date] = day.split('-')
  return `${date}/${month}/${year}`
}

export function TrackerRhythm({ dashboard, trackers }: { dashboard: DashboardResponse; trackers: Tracker[] }) {
  const [mode, setMode] = useState<'week' | 'month'>('week')
  const [week, setWeek] = useState(0)
  const [showAll, setShowAll] = useState(false)
  const [selectedTracker, setSelectedTracker] = useState<string | null>(trackers[0]?.id ?? null)
  const [selected, setSelected] = useState<{ trackerId: string; day: string } | null>(null)
  const days = useMemo(() => daysInReportMonth(dashboard.activity_month), [dashboard.activity_month])
  const offset = reportMonthOffset(dashboard.activity_month)
  const totalWeeks = Math.ceil((offset + days.length) / 7)
  const counts = useMemo(() => activityCountByTrackerDay(dashboard.activity_days), [dashboard.activity_days])
  const visibleTrackers = showAll ? trackers : trackers.slice(0, 4)
  const selectedTrackerRow = trackers.find((tracker) => tracker.id === selectedTracker) ?? trackers[0] ?? null
  const weekDays = Array.from({ length: 7 }, (_, index) => days[week * 7 + index - offset] ?? null)
  const countAt = (trackerId: string, day: string) => counts.get(`${trackerId}:${day}`) ?? 0
  const selectDay = (trackerId: string, day: string) => setSelected({ trackerId, day })

  if (trackers.length === 0) return <section data-testid="tracker-rhythm" className="border-t border-muted pt-3"><h3 className="text-sm font-bold">Nhịp ghi theo ngày</h3><p className="mt-2 text-sm text-muted-foreground">Chưa có tracker để xem nhịp ghi.</p></section>

  const renderDayButton = (tracker: Tracker, day: string, full = false) => {
    const count = countAt(tracker.id, day)
    const future = isFutureActivityDay(day)
    const active = selected?.trackerId === tracker.id && selected.day === day
    return <Button key={day} size="lg" variant={active ? 'selected' : 'ghost'} disabled={future} aria-pressed={active} data-testid="rhythm-day" data-count={count} className={cn('min-w-6 w-full min-h-11 p-0', full && 'flex-col gap-1 py-1')} aria-label={`${tracker.name}, ${vietnamDate(day)}: ${future ? 'chưa tới' : `${count} lần ghi`}`} onClick={() => selectDay(tracker.id, day)}>{full ? <span className="text-xs text-muted-foreground">{Number(day.slice(-2))}</span> : null}<span aria-hidden="true" className={cn('flex size-5 items-center justify-center rounded-full text-xs font-bold', future ? 'text-muted-foreground' : count > 0 ? 'bg-primary text-primary-foreground' : 'border border-input text-muted-foreground')}>{future ? '–' : count || ''}</span></Button>
  }

  const selectedCount = selected ? countAt(selected.trackerId, selected.day) : null
  const selectedName = selected ? trackers.find((tracker) => tracker.id === selected.trackerId)?.name ?? 'Tracker' : null
  const hasEntries = dashboard.activity_days.length > 0

  return <section data-testid="tracker-rhythm" className="space-y-4 border-t border-muted pt-3"><div><h3 className="text-sm font-bold">Nhịp ghi theo ngày</h3><p className="mt-1 text-xs text-muted-foreground">{dashboard.activity_month} · mỗi chấm là số lần đã ghi, không phải mức độ hoàn thành.</p></div>
    <div className="flex flex-wrap gap-1" role="group" aria-label="Cách xem nhịp ghi"><Button size="lg" variant={mode === 'week' ? 'selected' : 'outline'} aria-pressed={mode === 'week'} onClick={() => setMode('week')}>Nhiều tracker</Button><Button size="lg" variant={mode === 'month' ? 'selected' : 'outline'} aria-pressed={mode === 'month'} onClick={() => setMode('month')}>Một tracker</Button></div>
    {!hasEntries ? <p data-testid="rhythm-empty" className="rounded-lg bg-muted/50 p-3 text-sm text-muted-foreground">Chưa có bản ghi trong tháng này. Ô trống chỉ cho biết chưa có bản ghi, không kết luận đã bỏ lỡ lời nhắc.</p> : null}
    {mode === 'week' ? <><div className="flex items-center justify-between gap-2"><Button size="lg" variant="outline" className="size-11 p-0" aria-label="Tuần trước" disabled={week === 0} onClick={() => setWeek((value) => value - 1)}><ChevronLeft /></Button><p className="text-sm font-bold">Tuần {week + 1} / {totalWeeks}</p><Button size="lg" variant="outline" className="size-11 p-0" aria-label="Tuần sau" disabled={week >= totalWeeks - 1} onClick={() => setWeek((value) => value + 1)}><ChevronRight /></Button></div><div role="table" aria-label="Bản ghi từng tracker trong tuần" className="w-full"><div role="row" className="grid grid-cols-[minmax(64px,1.4fr)_repeat(7,minmax(0,1fr))] gap-x-1 pb-2 text-center text-xs text-muted-foreground"><span role="columnheader" className="self-end text-left">Tracker</span>{weekDays.map((day, index) => <span role="columnheader" key={WEEKDAYS[index]}>{WEEKDAYS[index]}<span className="mt-1 block font-semibold text-foreground">{day ? Number(day.slice(-2)) : '—'}</span></span>)}</div>{visibleTrackers.map((tracker) => <div role="row" key={tracker.id} className="grid grid-cols-[minmax(64px,1.4fr)_repeat(7,minmax(0,1fr))] items-center gap-x-1 border-t border-muted py-1"><span role="rowheader" className="min-w-0 break-words pr-1 text-xs font-semibold sm:text-sm">{tracker.name}</span>{weekDays.map((day, index) => <span role="cell" key={`${tracker.id}-${index}`}>{day ? renderDayButton(tracker, day) : null}</span>)}</div>)}</div>{trackers.length > 4 ? <Button size="lg" variant="ghost" onClick={() => setShowAll((value) => !value)}>{showAll ? 'Thu gọn còn 4 tracker' : `Xem thêm ${trackers.length - 4} tracker`}</Button> : null}</> : <><Select value={selectedTrackerRow?.id} onValueChange={(value) => { setSelectedTracker(value); setSelected(null) }}><SelectTrigger size="lg" className="w-full min-w-0" aria-label="Tracker cần xem"><SelectValue /></SelectTrigger><SelectContent>{trackers.map((tracker) => <SelectItem key={tracker.id} value={tracker.id}>{tracker.name}</SelectItem>)}</SelectContent></Select>{selectedTrackerRow ? <div><p className="mb-2 text-sm text-muted-foreground"><b className="text-foreground">{days.filter((day) => countAt(selectedTrackerRow.id, day) > 0).length} ngày có ghi</b> · {days.reduce((sum, day) => sum + countAt(selectedTrackerRow.id, day), 0)} bản ghi trong tháng</p><div className="grid grid-cols-7 gap-1 text-center">{WEEKDAYS.map((label) => <span key={label} className="text-xs text-muted-foreground">{label}</span>)}{Array.from({ length: offset }, (_, index) => <span key={`empty-${index}`} />)}{days.map((day) => renderDayButton(selectedTrackerRow, day, true))}</div></div> : null}</>}
    <div className="flex flex-wrap gap-x-4 gap-y-2 border-t border-muted pt-3 text-xs text-muted-foreground" aria-label="Chú giải"><span><span aria-hidden="true" className="mr-2 inline-flex size-5 items-center justify-center rounded-full bg-primary text-primary-foreground">1</span>Số lần ghi</span><span><span aria-hidden="true" className="mr-2 inline-block size-5 rounded-full border border-input" />Chưa có bản ghi</span><span>– Ngày chưa tới</span></div>
    <div role="status" aria-live="polite" data-testid="rhythm-detail" className="rounded-lg bg-muted/50 p-3 text-sm">{selected ? <><p className="font-bold">{selectedName} · {vietnamDate(selected.day)}</p><p className="mt-1 text-muted-foreground">{selectedCount ? `${selectedCount} lần ghi trong ngày.` : 'Chưa có bản ghi cho ngày này.'}</p></> : <p className="text-muted-foreground">Chọn một chấm để xem ngày và số lần ghi.</p>}</div>
    <p className="text-xs text-muted-foreground">Chấm trống không có nghĩa là bỏ lỡ lời nhắc. Lịch nhắc theo chu kỳ vẫn được xem riêng.</p>
  </section>
}
