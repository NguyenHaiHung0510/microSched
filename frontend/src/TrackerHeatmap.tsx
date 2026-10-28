import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { Popover as PopoverPrimitive } from 'radix-ui'
import { ArrowRight, ChevronLeft, ChevronRight, Coins, Hash, Heart, Sparkles } from 'lucide-react'
import { apiRequest } from '@/api'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent } from '@/components/ui/popover'
import { groupHeatmapEntries, heatmapDateLabel, heatmapEntryValue, heatmapGroupTotal, heatmapKindLabel } from '@/tracker-heatmap'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { daysInReportMonth } from '@/tracker-rhythm'
import { activityLevel, initialHeatmapMonth, initialRecordsSelection, periodBounds } from '@/tracker-records'
import { standardRefetchInterval } from '@/query-polling'
import { trackerQueryKey, type Entry, type Tracker, type TrackerGroup } from '@/tracker-ui'

type Activity = { day: string; count: number }
const WEEKDAYS = ['T2','T3','T4','T5','T6','T7','CN']
const LEVELS = ['0','1','2','≥3']
// Scope labels stay readable without changing the shared Select defaults.
const scopeSelectTriggerClass = 'min-h-11 w-full min-w-0 [&_[data-slot=select-value]]:min-w-0 [&_[data-slot=select-value]]:flex-1 [&_[data-slot=select-value]>span]:truncate'
const scopeSelectContentClass = 'w-(--radix-select-trigger-width) min-w-0 max-w-(--radix-select-content-available-width) data-[side=bottom]:translate-y-0 data-[side=top]:translate-y-0 [&_[data-radix-select-viewport]]:min-w-0'
const scopeSelectItemClass = 'min-h-11 whitespace-normal [&>span:last-child]:min-w-0 [&>span:last-child]:block'
// Touch focus stays on content so scroll-button mounts cannot scroll the focused option back into view.

function daysInYear(year: number): string[] {
  if (year < 1 || year > 9998) return []
  const day = new Date(`${String(year).padStart(4,'0')}-01-01T00:00:00Z`)
  const result: string[] = []
  while (day.getUTCFullYear() === year) { result.push(day.toISOString().slice(0,10)); day.setUTCDate(day.getUTCDate()+1) }
  return result
}

function entryTimeDisplay(occurredAt: string | null): string | null {
  if (!occurredAt) return null
  try {
    return new Intl.DateTimeFormat('vi-VN', {
      timeZone: 'Asia/Ho_Chi_Minh',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(occurredAt))
  } catch {
    return null
  }
}

function HeatmapDayDetail({
  day,
  count,
  trackerId,
  groupId,
  trackers,
  privateUnlocked,
  today,
  onJump,
  mode = 'dialog',
}: {
  day: string
  count: number
  trackerId: string
  groupId?: string
  trackers: Tracker[]
  privateUnlocked: boolean
  today: string
  onJump: () => void
  mode?: 'tooltip' | 'dialog'
}) {
  const isFuture = day > today
  const bounds = useMemo(() => periodBounds('day', day), [day])
  const query = useInfiniteQuery({
    queryKey: [...trackerQueryKey('entries'), 'heatmap-day-preview', privateUnlocked, trackerId, groupId, day],
    initialPageParam: 0,
    queryFn: ({ signal, pageParam }) => {
      const params = new URLSearchParams({
        from: bounds!.from, to: bounds!.to, limit: '51', offset: String(pageParam), order: 'asc',
      })
      if (trackerId !== 'all') params.set('tracker_id', trackerId)
      if (groupId) params.set('group_id', groupId)
      return apiRequest<{ items: Entry[] }>(`/api/tracker/entries?${params}`, { signal })
    },
    getNextPageParam: (lastPage, _pages, offset) => lastPage.items.length > 50 ? offset + 50 : undefined,
    enabled: count > 0 && bounds !== null && !isFuture,
    staleTime: 30_000,
  })
  const entries = query.data?.pages.flatMap(page => page.items.slice(0, 50)) ?? []
  const groups = groupHeatmapEntries(entries, trackers, trackerId, privateUnlocked)
  const partial = query.hasNextPage

  return (
    <div data-testid="heatmap-day-detail" className="min-w-0 space-y-3 text-left text-sm leading-relaxed text-foreground">
      <div className="border-b border-border/30 pb-3">
        <p className="text-base font-bold" data-testid="heatmap-detail-date">{heatmapDateLabel(day)}</p>
        <p className="text-xs text-muted-foreground" data-testid="heatmap-detail-count">
          {isFuture ? 'Ngày chưa tới' : `${count} lần ghi`}
          {trackerId === 'all' && !partial && !query.isPending && !query.isError && groups.length > 0 ? ` · ${groups.length} tracker` : ''}
        </p>
      </div>
      {isFuture ? <p className="text-muted-foreground">Ngày chưa tới: không thể xem hoặc chọn.</p>
        : count === 0 ? <p className="text-muted-foreground">Chưa có bản ghi nào trong ngày này.</p>
        : query.isPending ? <p role="status" data-testid="heatmap-detail-loading" className="text-muted-foreground">Đang tải chi tiết…</p>
        : query.isError && !query.data ? (
          <div className="space-y-2">
            <p role="alert" data-testid="heatmap-detail-error" className="text-bad">Không tải được chi tiết. Thử tải lại.</p>
            <Button data-testid="heatmap-detail-retry" size="sm" variant="outline" onClick={() => void query.refetch()}>Thử lại</Button>
          </div>
        ) : groups.length === 0 ? <p className="text-muted-foreground">Không tìm thấy bản ghi.</p> : (
          <div className="max-h-72 space-y-3 overflow-y-auto overscroll-contain" data-testid="heatmap-detail-entries" tabIndex={0} role="region" aria-label="Bản ghi trong ngày">
            {partial ? <p className="text-xs text-muted-foreground">Đang hiển thị {entries.length}/{count} lần ghi; tổng nhóm tính theo phần đã tải.</p> : null}
            {groups.map(({ tracker, entries: rows }) => {
              const Icon = tracker.kind === 'finance' ? Coins : tracker.kind === 'health' ? Heart : tracker.input_mode === 'quantity' ? Hash : Sparkles
              return <section key={tracker.id} data-testid="heatmap-detail-group" data-tracker-id={tracker.id} className="space-y-2 border-b border-border/20 pb-3 last:border-0 last:pb-0">
                <div className="flex items-start gap-2">
                  <span aria-hidden="true" className="flex size-9 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground"><Icon className="size-5" /></span>
                  <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1 pt-1">
                    <span className="min-w-0 font-bold [overflow-wrap:anywhere]">{tracker.name}</span>
                    <span className="rounded-full bg-accent px-2 py-0.5 text-xs text-accent-foreground">{heatmapKindLabel(tracker)}</span>
                  </div>
                  <span data-testid="heatmap-group-total" className="max-w-[45%] shrink-0 pt-1 text-right font-bold tabular-nums [overflow-wrap:anywhere]">{heatmapGroupTotal(rows, tracker)}</span>
                </div>
                <div className="space-y-2 sm:pl-11">
                  {rows.map(entry => <div key={entry.id} data-testid="heatmap-detail-entry" data-entry-id={entry.id} className="flex items-start gap-3 text-xs">
                    <p className="min-w-0 flex-1 whitespace-pre-wrap text-muted-foreground [overflow-wrap:anywhere]">
                      <span className="tabular-nums">{entryTimeDisplay(entry.occurred_at) ?? 'Chưa có giờ'}</span>
                      {' · '}{entry.note_md || 'Không có ghi chú'}
                    </p>
                    <span className="max-w-[40%] shrink-0 text-right tabular-nums [overflow-wrap:anywhere]">{heatmapEntryValue(entry, tracker)}</span>
                  </div>)}
                </div>
              </section>
            })}
            {query.isFetchNextPageError ? <p role="alert" className="text-xs text-bad">Không tải được phần tiếp theo. Thử lại.</p> : null}
            {partial ? <Button data-testid="heatmap-detail-more" variant="outline" size="sm" disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>{query.isFetchingNextPage ? 'Đang tải…' : 'Xem thêm bản ghi'}</Button> : null}
          </div>
        )}
      {!isFuture && count > 0 ? (
        <Button data-testid="heatmap-detail-jump" variant="link" className="h-auto min-h-11 w-full justify-start whitespace-normal rounded-none border-0 border-t border-border/30 px-0 pt-3 text-sm" onClick={onJump}>
          {mode === 'tooltip' ? 'Xem đầy đủ bản ghi' : 'Xem chi tiết trong bảng bản ghi'}<ArrowRight aria-hidden="true" />
        </Button>
      ) : null}
    </div>
  )
}
function AnnualHeatmap({ yearDays, yearOffset, counts, today, trackerId, groupId, trackers, privateUnlocked, onDay, onTouch }: {
  yearDays: string[]; yearOffset: number; counts: Map<string, number>; today: string
  trackerId: string; trackers: Tracker[]; privateUnlocked: boolean
  groupId?: string
  onDay: (trackerId: string, day: string, groupId?: string) => void; onTouch: (day: string) => void
}) {
  const [preview, setPreview] = useState<{ day: string; element: SVGRectElement } | null>(null)
  const [focusDay, setFocusDay] = useState(() => yearDays.includes(today) ? today : yearDays.find(day => day <= today))
  const closeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const contentRef = useRef<HTMLDivElement>(null)
  const touchPointer = useRef(false)
  const restoreOnClose = useRef(false)
  const suppressPreviewFocus = useRef(false)
  const hintId = useId()
  const previewId = useId()
  const keepOpen = () => clearTimeout(closeTimer.current)
  const closeSoon = () => {
    keepOpen()
    closeTimer.current = setTimeout(() => {
      if (!contentRef.current?.contains(document.activeElement)) setPreview(null)
    }, 220)
  }
  const show = (day: string, element: SVGRectElement) => {
    keepOpen()
    setPreview({ day, element })
  }
  useEffect(() => () => clearTimeout(closeTimer.current), [])

  return <div className="hidden space-y-2 sm:block" data-testid="heatmap-year-overview">
    <div className="flex justify-between text-xs text-muted-foreground" aria-hidden="true">{Array.from({ length: 12 }, (_, i) => <span key={i}>T{i + 1}</span>)}</div>
    <p id={hintId} className="sr-only">Dùng phím mũi tên để chọn ngày, Home và End để đến đầu hoặc cuối năm. Enter hoặc Space xem đầy đủ bản ghi, F2 vào chi tiết, Escape đóng. Có thể chọn tháng và ngày ở bên dưới.</p>
    <Popover open={preview !== null} onOpenChange={open => { if (!open) { keepOpen(); setPreview(null) } }}>
      {preview ? <PopoverPrimitive.Anchor virtualRef={{ current: preview.element }} /> : null}
      <svg viewBox={`0 0 ${Math.ceil((yearDays.length + yearOffset) / 7) * 14} 98`} role="group" aria-label={`Tổng quan năm ${yearDays[0]?.slice(0, 4)}`} aria-describedby={hintId} className="w-full">
        {yearDays.map((day, i) => {
          const count = counts.get(day) ?? 0
          const future = day > today
          return <rect key={day} x={Math.floor((i + yearOffset) / 7) * 14} y={((i + yearOffset) % 7) * 14} width="12" height="12" rx="2"
            data-testid="heatmap-year-day" data-day={day} data-count={count} data-level={activityLevel(count)}
            fill={`var(--heatmap-${activityLevel(count)})`} opacity={future ? 0.3 : 1}
            role="button" aria-label={`${heatmapDateLabel(day)}: ${future ? 'chưa tới' : `${count} lần ghi, xem bản ghi`}`}
            aria-disabled={future} aria-haspopup="dialog" aria-expanded={preview?.day === day} aria-controls={preview?.day === day ? previewId : undefined}
            tabIndex={!future && day === focusDay ? 0 : -1}
            className={`outline-none focus:stroke-ring focus:stroke-2 ${preview?.day === day ? 'stroke-ring stroke-2' : ''} ${future ? '' : 'cursor-pointer'}`}
            onPointerEnter={event => { if (!future && event.pointerType !== 'touch') show(day, event.currentTarget) }}
            onPointerLeave={closeSoon}
            onPointerDown={event => { touchPointer.current = event.pointerType === 'touch' }}
            onFocus={event => { if (!future && !touchPointer.current && !suppressPreviewFocus.current) { setFocusDay(day); show(day, event.currentTarget) } }}
            onBlur={closeSoon}
            onClick={event => {
              if (future) return
              if (touchPointer.current) { setPreview(null); onTouch(day) }
              else { setPreview(null); onDay(trackerId, day, groupId) }
              event.preventDefault()
            }}
            onKeyDown={event => {
              if (future) return
              touchPointer.current = false
              if (event.key === 'Escape') { keepOpen(); setPreview(null); event.preventDefault(); return }
              if (event.key === 'Enter' || event.key === ' ') { setPreview(null); onDay(trackerId, day, groupId); event.preventDefault(); return }
              if (event.key === 'F2') { show(day, event.currentTarget); requestAnimationFrame(() => contentRef.current?.querySelector<HTMLElement>('button, [tabindex="0"]')?.focus()); event.preventDefault(); return }
              const deltas: Record<string, number> = { ArrowUp: -1, ArrowDown: 1, ArrowLeft: -7, ArrowRight: 7 }
              const last = yearDays.filter(value => value <= today).length - 1
              const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? last : event.key in deltas ? Math.max(0, Math.min(last, i + deltas[event.key])) : null
              if (nextIndex === null) return
              event.preventDefault()
              const nextDay = yearDays[nextIndex]
              setFocusDay(nextDay)
              event.currentTarget.ownerSVGElement?.querySelector<SVGRectElement>(`[data-day="${nextDay}"]`)?.focus()
            }} />
        })}
      </svg>
      {preview ? <PopoverContent ref={contentRef} id={previewId} data-testid="heatmap-year-preview" side="bottom" align="center" sideOffset={10}
        className="w-[min(440px,calc(100vw-24px))] rounded-2xl border-border/20 bg-card p-4 text-foreground shadow-2"
        aria-label={`Bản ghi ${heatmapDateLabel(preview.day)}`}
        onOpenAutoFocus={event => event.preventDefault()}
        onEscapeKeyDown={() => { restoreOnClose.current = true }}
        onCloseAutoFocus={event => {
          event.preventDefault()
          if (restoreOnClose.current) {
            suppressPreviewFocus.current = true
            preview.element.focus({ preventScroll: true })
            suppressPreviewFocus.current = false
            restoreOnClose.current = false
          }
        }}
        onPointerEnter={keepOpen} onPointerLeave={closeSoon} onFocusCapture={keepOpen} onBlurCapture={closeSoon}
        onInteractOutside={event => { if (event.target instanceof Element && event.target.closest('[data-testid="heatmap-year-overview"]')) event.preventDefault() }}>
        <HeatmapDayDetail day={preview.day} count={counts.get(preview.day) ?? 0} trackerId={trackerId} groupId={groupId} trackers={trackers} privateUnlocked={privateUnlocked} today={today}
          onJump={() => { const day = preview.day; setPreview(null); onDay(trackerId, day, groupId) }} mode="tooltip" />
      </PopoverContent> : null}
    </Popover>
  </div>
}

export function TrackerHeatmap({ trackers, groups, initialMonth, onDay, privateUnlocked }: { trackers: Tracker[]; groups: TrackerGroup[]; initialMonth: string; onDay: (trackerId: string, day: string, groupId?: string) => void; privateUnlocked: boolean }) {
  const [yearText,setYearText] = useState(initialMonth.slice(0,4))
  const year = Number(yearText)
  const validYear = /^[0-9]{1,4}$/.test(yearText) && year >= 1 && year <= 9998
  const [month,setMonth] = useState(initialMonth)
  const [scope,setScope] = useState<'all' | 'group' | 'tracker'>('all')
  const [selectedTracker,setSelectedTracker] = useState('')
  const [selectedGroup,setSelectedGroup] = useState('')
  const trackerId = scope === 'tracker' ? selectedTracker : 'all'
  const groupId = scope === 'group' ? selectedGroup : undefined
  const visibleTrackers = trackers.filter(tracker => privateUnlocked || !tracker.is_private)
  const scopeReady = scope === 'all' || (scope === 'group'
    ? groups.some(group => group.id === groupId)
    : visibleTrackers.some(tracker => tracker.id === trackerId))
  const scopeKey = `${scope}:${groupId ?? trackerId}`
  const [touchDetailDay, setTouchDetailDay] = useState<string | null>(null)
  const query = useQuery({
    queryKey: ['tracker','activity',privateUnlocked,yearText,scopeKey],
    queryFn: ({signal}) => {
      const params = new URLSearchParams({ year: String(year) })
      if (trackerId !== 'all') params.set('tracker_id', trackerId)
      if (groupId) params.set('group_id', groupId)
      return apiRequest<{items: Activity[]}>(`/api/tracker/activity?${params}`,{signal})
    },
    enabled: validYear && scopeReady,
    refetchInterval: standardRefetchInterval,
  })
  const counts = useMemo(() => new Map(query.data?.items.map(row=>[row.day,row.count]) ?? []), [query.data])
  const yearDays = useMemo(()=>validYear ? daysInYear(year) : [],[validYear,year])
  const days = daysInReportMonth(month)
  const offset = (new Date(`${month}-01T00:00:00Z`).getUTCDay()+6)%7
  const yearOffset = yearDays.length ? (new Date(yearDays[0]+'T00:00:00Z').getUTCDay()+6)%7 : 0
  const today = initialRecordsSelection().anchor
  const total = [...counts.values()].reduce((sum,n)=>sum+n,0)
  const shiftMonth = (delta: number) => {
    const next = new Date(month+'-01T00:00:00Z'); next.setUTCMonth(next.getUTCMonth()+delta)
    setMonth(next.toISOString().slice(0,7))
  }
  return <Card data-testid="tracker-heatmap" className="gap-4 p-4 shadow-1 ring-0">
    <div><h3 className="text-base font-bold">Heatmap số lần ghi</h3><p className="mt-1 text-xs text-muted-foreground">Mỗi ô là một ngày theo giờ Việt Nam. Màu đậm hơn là nhiều lần ghi hơn.</p></div>
    <div role="group" aria-label="Phạm vi heatmap" className="grid grid-cols-3 gap-1 rounded-xl bg-muted p-1 sm:w-fit">
      {([['all', 'Tất cả'], ['group', 'Nhóm'], ['tracker', 'Tracker']] as const).map(([value, label]) =>
        <Button key={value} data-testid={`heatmap-scope-${value}`} aria-pressed={scope === value} variant={scope === value ? 'selected' : 'ghost'} className="min-h-11 min-w-0 sm:min-w-24" onClick={() => {
          setTouchDetailDay(null)
          setScope(value)
          if (value === 'group' && !groups.some(group => group.id === selectedGroup)) setSelectedGroup(groups[0]?.id ?? '')
          if (value === 'tracker' && !visibleTrackers.some(tracker => tracker.id === selectedTracker)) setSelectedTracker(visibleTrackers[0]?.id ?? '')
        }}>{label}</Button>)}
    </div>
    <div className="grid gap-3 sm:grid-cols-2">
      {scope === 'group' ? <label className="min-w-0 space-y-1 text-sm font-semibold"><span>Nhóm</span>
        <Select value={scopeReady ? selectedGroup : ''} onValueChange={value => { setTouchDetailDay(null); setSelectedGroup(value) }} disabled={!groups.length}><SelectTrigger data-testid="heatmap-group" className={scopeSelectTriggerClass}><SelectValue placeholder="Chọn nhóm" /></SelectTrigger><SelectContent position="popper" align="start" sideOffset={4} collisionPadding={8} className={scopeSelectContentClass} onTouchStart={event => event.currentTarget.focus({ preventScroll: true })}>{groups.map(group => <SelectItem key={group.id} value={group.id} className={scopeSelectItemClass}><span className="block [overflow-wrap:anywhere]">{group.name} · {visibleTrackers.filter(tracker => tracker.group_id === group.id).length} tracker</span></SelectItem>)}</SelectContent></Select>
      </label> : scope === 'tracker' ? <label className="min-w-0 space-y-1 text-sm font-semibold"><span>Tracker</span>
        <Select value={scopeReady ? selectedTracker : ''} onValueChange={value => { setTouchDetailDay(null); setSelectedTracker(value) }} disabled={!visibleTrackers.length}><SelectTrigger data-testid="heatmap-tracker" className={scopeSelectTriggerClass}><SelectValue placeholder="Chọn tracker" /></SelectTrigger><SelectContent position="popper" align="start" sideOffset={4} collisionPadding={8} className={scopeSelectContentClass} onTouchStart={event => event.currentTarget.focus({ preventScroll: true })}>{visibleTrackers.map(t=><SelectItem key={t.id} value={t.id} className={scopeSelectItemClass}><span className="block [overflow-wrap:anywhere]">{t.name}</span></SelectItem>)}</SelectContent></Select>
      </label> : null}
      <label className="min-w-0 space-y-1 text-sm font-semibold"><span>Năm</span><Input data-testid="heatmap-year" type="number" min={1} max={9998} className="min-h-11 text-base" value={yearText} onChange={e=>{
        const value=e.target.value;setTouchDetailDay(null);setYearText(value)
        if (/^[0-9]{1,4}$/.test(value) && Number(value)>=1 && Number(value)<=9998) setMonth(initialHeatmapMonth(Number(value)))
      }} /></label>
    </div>
    {!validYear ? <p role="alert" className="text-sm text-bad">Chọn năm từ 1 đến 9998.</p> : !scopeReady ? <p role="status" className="text-sm text-muted-foreground">{scope === 'group' ? 'Chọn một nhóm hiện có để xem heatmap. Nhóm đã xoá không còn bản ghi trong phạm vi này.' : 'Chọn một tracker hiện có để xem heatmap.'}</p> : query.isError ? <div role="alert" className="space-y-2"><p className="text-sm text-bad">Không tải được heatmap.</p><Button variant="outline" className="min-h-11" onClick={()=>void query.refetch()}>Thử lại</Button></div> : query.isPending ? <p role="status" className="text-sm text-muted-foreground">Đang tải heatmap…</p> : <>
      <p role="status" className="text-sm text-muted-foreground" data-testid="heatmap-summary">{total} lần ghi trong năm {year} · {counts.size} ngày có bản ghi</p>
      <AnnualHeatmap key={`${yearText}-${scopeKey}`} yearDays={yearDays} yearOffset={yearOffset} counts={counts} today={today} trackerId={trackerId} groupId={groupId} trackers={visibleTrackers} privateUnlocked={privateUnlocked} onDay={onDay} onTouch={setTouchDetailDay} />
      <div className="flex flex-wrap items-end justify-between gap-2">
        <label className="min-w-0 space-y-1 text-sm font-semibold"><span>Tháng chi tiết</span><Input data-testid="heatmap-month" type="month" min={`${String(year).padStart(4,'0')}-01`} max={`${String(year).padStart(4,'0')}-12`} className="min-h-11 text-base" value={month} onChange={e=>{
          const value=e.target.value
          if (/^\d{4}-(0[1-9]|1[0-2])$/.test(value) && Number(value.slice(0,4))===year) setMonth(value)
        }} /></label>
        <div className="flex gap-2"><Button variant="outline" size="icon-lg" className="size-11" aria-label="Tháng heatmap trước" disabled={month.endsWith('-01')} onClick={()=>shiftMonth(-1)}><ChevronLeft /></Button><Button variant="outline" size="icon-lg" className="size-11" aria-label="Tháng heatmap sau" disabled={month.endsWith('-12')} onClick={()=>shiftMonth(1)}><ChevronRight /></Button></div>
      </div>
      <p className="text-xs text-muted-foreground sm:hidden">Vuốt ngang lịch để xem đủ 7 ngày trong tuần.</p>
      <TooltipProvider delayDuration={150}>
        <div className="overflow-x-auto pb-2"><div className="grid min-w-[356px] grid-cols-7 gap-2" data-testid="heatmap-month-grid">
          {WEEKDAYS.map(day=><span key={day} className="py-1 text-center text-xs text-muted-foreground">{day}</span>)}
          {Array.from({length:offset},(_,i)=><span aria-hidden="true" key={'blank-' + i} />)}
          {days.map(day=>{
            const count=counts.get(day)??0;const level=activityLevel(count);const future=day>today
            return (
              <Tooltip key={day}>
                <TooltipTrigger asChild>
                  <Button
                    data-testid="heatmap-day"
                    data-day={day}
                    data-count={count}
                    data-level={level}
                    variant="ghost"
                    className="h-auto min-h-11 min-w-11 flex-col gap-1 p-1"
                    disabled={future}
                    aria-label={`${day}: ${future ? 'chưa tới' : `${count} lần ghi, xem bản ghi`}`}
                    onClick={(e)=>{
                      const isTouch = e.nativeEvent instanceof PointerEvent && e.nativeEvent.pointerType === 'touch'
                      if (isTouch) {
                        setTouchDetailDay(day)
                      } else {
                        onDay(trackerId,day,groupId)
                      }
                    }}
                  >
                    <span className="text-xs">{Number(day.slice(-2))}</span>
                    <span aria-hidden="true" className="size-4 rounded-sm ring-1 ring-border/50" style={{backgroundColor:`var(--heatmap-${level})`}} />
                    {count>0 ? <span className="text-xs tabular-nums">{count}</span> : null}
                  </Button>
                </TooltipTrigger>
                <TooltipContent data-testid="heatmap-tooltip" side="top" className="w-[min(440px,calc(100vw-24px))] max-w-none rounded-2xl p-4 shadow-2 bg-card text-foreground border border-border/20">
                  <HeatmapDayDetail
                    day={day}
                    count={count}
                    trackerId={trackerId}
                    groupId={groupId}
                    trackers={visibleTrackers}
                    privateUnlocked={privateUnlocked}
                    today={today}
                    onJump={()=>onDay(trackerId,day,groupId)}
                    mode="tooltip"
                  />
                </TooltipContent>
              </Tooltip>
            )
          })}
        </div></div>
      </TooltipProvider>
      <Dialog open={touchDetailDay !== null} onOpenChange={(open) => !open && setTouchDetailDay(null)}>
        <DialogContent data-testid="heatmap-touch-detail" className="max-h-[85vh] overflow-y-auto sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Chi tiết bản ghi ngày</DialogTitle>
          </DialogHeader>
          {touchDetailDay ? (
            <HeatmapDayDetail
              day={touchDetailDay}
              count={counts.get(touchDetailDay) ?? 0}
              trackerId={trackerId}
              groupId={groupId}
              trackers={visibleTrackers}
              privateUnlocked={privateUnlocked}
              today={today}
              onJump={() => {
                const d = touchDetailDay
                setTouchDetailDay(null)
                onDay(trackerId, d, groupId)
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-muted-foreground" aria-label="Thang màu heatmap">
        {LEVELS.map((label,i)=><span key={label} className="inline-flex items-center gap-1"><span aria-hidden="true" className="size-4 rounded-sm ring-1 ring-border/50" style={{backgroundColor:`var(--heatmap-${i})`}} />{label} lần</span>)}<span>Ngày chưa tới: không chọn được</span>
      </div>
      {!counts.size ? <p className="text-sm text-muted-foreground">Chưa có bản ghi trong năm này.</p> : null}
    </>}
  </Card>
}
