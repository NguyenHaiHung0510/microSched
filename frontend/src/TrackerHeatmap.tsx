import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight } from 'lucide-react'
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
import { formatQuantity, formatVnd, trackerQueryKey, type Entry, type Tracker } from '@/tracker-ui'

type Activity = { day: string; count: number }
const WEEKDAYS = ['T2','T3','T4','T5','T6','T7','CN']
const LEVELS = ['0','1','2','≥3']
function daysInYear(year: number): string[] {
  if (year < 1 || year > 9998) return []
  const day = new Date(`${String(year).padStart(4,'0')}-01-01T00:00:00Z`)
  const result: string[] = []
  while (day.getUTCFullYear() === year) { result.push(day.toISOString().slice(0,10)); day.setUTCDate(day.getUTCDate()+1) }
  return result
}

function trackerKindLabel(tracker?: Tracker): string {
  if (!tracker) return 'Bản ghi'
  if (tracker.kind === 'finance') {
    return tracker.direction === 'in' ? 'Thu nhập' : 'Chi tiêu'
  }
  if (tracker.kind === 'health') return 'Sức khỏe'
  if (tracker.input_mode === 'quantity') return 'Số lượng'
  return 'Thói quen'
}

function entryValueDisplay(entry: Entry, tracker?: Tracker): string | null {
  if (entry.amount != null) {
    return formatVnd(entry.amount)
  }
  if (entry.quantity != null) {
    return `${formatQuantity(entry.quantity)}${tracker?.unit ? ' ' + tracker.unit : ''}`
  }
  return null
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
  trackers,
  privateUnlocked,
  today,
  onJump,
  mode = 'dialog',
}: {
  day: string
  count: number
  trackerId: string
  trackers: Tracker[]
  privateUnlocked: boolean
  today: string
  onJump: () => void
  mode?: 'tooltip' | 'dialog'
}) {
  const isFuture = day > today
  const bounds = useMemo(() => periodBounds('day', day), [day])
  const query = useQuery({
    queryKey: [...trackerQueryKey('entries'), 'heatmap-detail', privateUnlocked, trackerId, day],
    queryFn: ({ signal }) => {
      const params = new URLSearchParams({
        from: bounds!.from,
        to: bounds!.to,
        limit: '500',
      })
      if (trackerId !== 'all') params.set('tracker_id', trackerId)
      return apiRequest<{ items: Entry[] }>(`/api/tracker/entries?${params.toString()}`, { signal })
    },
    enabled: count > 0 && bounds !== null && !isFuture,
    staleTime: 30_000,
  })

  const trackerMap = useMemo(() => new Map(trackers.map((t) => [t.id, t])), [trackers])

  return (
    <div data-testid="heatmap-day-detail" className="min-w-[220px] max-w-sm space-y-2 p-1 text-left text-xs text-foreground">
      <div className="border-b border-border/60 pb-1.5">
        <p className="font-bold text-foreground" data-testid="heatmap-detail-date">
          {day}
        </p>
        <p className="text-muted-foreground" data-testid="heatmap-detail-count">
          {isFuture ? 'Ngày chưa tới' : count === 0 ? '0 lần ghi trong ngày này' : `${count} lần ghi`}
        </p>
      </div>

      {isFuture ? (
        <p className="text-muted-foreground">Ngày chưa tới: không thể xem hoặc chọn.</p>
      ) : count === 0 ? (
        <p className="text-muted-foreground">Chưa có bản ghi nào trong ngày này.</p>
      ) : query.isPending ? (
        <p data-testid="heatmap-detail-loading" className="text-muted-foreground">Đang tải chi tiết…</p>
      ) : query.isError ? (
        <div className="space-y-1">
          <p data-testid="heatmap-detail-error" className="text-bad">Không tải được chi tiết.</p>
          <Button size="xs" variant="outline" onClick={() => void query.refetch()}>
            Thử lại
          </Button>
        </div>
      ) : query.data?.items.length === 0 ? (
        <p className="text-muted-foreground">Không tìm thấy bản ghi.</p>
      ) : (
        <div className="max-h-56 space-y-2 overflow-y-auto pr-1" data-testid="heatmap-detail-entries">
          {query.data?.items.map((entry) => {
            const tracker = trackerMap.get(entry.tracker_id)
            const val = entryValueDisplay(entry, tracker)
            const time = entryTimeDisplay(entry.occurred_at)
            return (
              <div
                key={entry.id}
                data-testid="heatmap-detail-entry"
                data-entry-id={entry.id}
                className="rounded-md border border-border/40 bg-card p-2 space-y-1"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-foreground">
                    {tracker?.name ?? 'Tracker'}
                    <span className="ml-1 text-[11px] font-normal text-muted-foreground">
                      ({trackerKindLabel(tracker)})
                    </span>
                  </span>
                  {val ? <span className="font-bold tabular-nums text-foreground">{val}</span> : null}
                </div>
                {entry.note_md ? (
                  <p className="whitespace-pre-wrap break-words text-xs text-muted-foreground">
                    {entry.note_md}
                  </p>
                ) : null}
                {time ? (
                  <p className="text-[10px] text-muted-foreground">Giờ ghi: {time}</p>
                ) : null}
              </div>
            )
          })}
        </div>
      )}

      {!isFuture && count > 0 ? (
        mode === 'tooltip' ? (
          <p className="mt-2 text-center text-[11px] text-muted-foreground">
            Nhấp ô ngày để xem trong bảng bản ghi
          </p>
        ) : (
          <Button
            data-testid="heatmap-detail-jump"
            size="sm"
            variant="secondary"
            className="mt-2 w-full text-xs font-semibold"
            onClick={onJump}
          >
            Xem chi tiết trong bảng bản ghi
          </Button>
        )
      ) : null}
    </div>
  )
}
export function TrackerHeatmap({ trackers, initialMonth, onDay, privateUnlocked }: { trackers: Tracker[]; initialMonth: string; onDay: (trackerId: string, day: string) => void; privateUnlocked: boolean }) {
  const [yearText,setYearText] = useState(initialMonth.slice(0,4))
  const year = Number(yearText)
  const validYear = /^[0-9]{1,4}$/.test(yearText) && year >= 1 && year <= 9998
  const [month,setMonth] = useState(initialMonth)
  const [trackerId,setTrackerId] = useState('all')
  const [touchDetailDay, setTouchDetailDay] = useState<string | null>(null)
  const query = useQuery({
    queryKey: ['tracker','activity',privateUnlocked,yearText,trackerId],
    queryFn: ({signal}) => apiRequest<{items: Activity[]}>(`/api/tracker/activity?year=${year}${trackerId==='all'?'':`&tracker_id=${trackerId}`}`,{signal}),
    enabled: validYear,
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
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="min-w-0 space-y-1 text-sm font-semibold"><span>Tracker</span>
        <Select value={trackerId} onValueChange={setTrackerId}><SelectTrigger data-testid="heatmap-tracker" className="min-h-11 w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Tất cả tracker</SelectItem>{trackers.map(t=><SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}</SelectContent></Select>
      </label>
      <label className="min-w-0 space-y-1 text-sm font-semibold"><span>Năm</span><Input data-testid="heatmap-year" type="number" min={1} max={9998} className="min-h-11 text-base" value={yearText} onChange={e=>{
        const value=e.target.value;setYearText(value)
        if (/^[0-9]{1,4}$/.test(value) && Number(value)>=1 && Number(value)<=9998) setMonth(initialHeatmapMonth(Number(value)))
      }} /></label>
    </div>
    {!validYear ? <p role="alert" className="text-sm text-bad">Chọn năm từ 1 đến 9998.</p> : query.isError ? <div role="alert" className="space-y-2"><p className="text-sm text-bad">Không tải được heatmap.</p><Button variant="outline" className="min-h-11" onClick={()=>void query.refetch()}>Thử lại</Button></div> : query.isPending ? <p role="status" className="text-sm text-muted-foreground">Đang tải heatmap…</p> : <>
      <p className="text-sm text-muted-foreground" data-testid="heatmap-summary">{total} lần ghi trong năm {year} · {counts.size} ngày có bản ghi</p>
      <div className="hidden space-y-2 sm:block" data-testid="heatmap-year-overview">
        <div className="flex justify-between text-xs text-muted-foreground" aria-hidden="true">{Array.from({length:12},(_,i)=><span key={i}>T{i+1}</span>)}</div>
        <svg viewBox={`0 0 ${Math.ceil((yearDays.length+yearOffset)/7)*14} 98`} role="img" aria-label={`Tổng quan năm ${year}: ${total} lần ghi; chọn tháng và ngày bên dưới để xem chi tiết`} className="w-full">
          {yearDays.map((day,i)=><rect key={day} x={Math.floor((i+yearOffset)/7)*14} y={((i+yearOffset)%7)*14} width="12" height="12" rx="2" data-day={day} data-level={activityLevel(counts.get(day)??0)} fill={`var(--heatmap-${activityLevel(counts.get(day)??0)})`} opacity={day>today?0.3:1} />)}
        </svg>
      </div>
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
                        onDay(trackerId,day)
                      }
                    }}
                  >
                    <span className="text-xs">{Number(day.slice(-2))}</span>
                    <span aria-hidden="true" className="size-4 rounded-sm ring-1 ring-border/50" style={{backgroundColor:`var(--heatmap-${level})`}} />
                    {count>0 ? <span className="text-xs tabular-nums">{count}</span> : null}
                  </Button>
                </TooltipTrigger>
                <TooltipContent data-testid="heatmap-tooltip" side="top" className="max-w-xs sm:max-w-sm p-2 shadow-2 bg-card text-foreground border border-border">
                  <HeatmapDayDetail
                    day={day}
                    count={count}
                    trackerId={trackerId}
                    trackers={trackers}
                    privateUnlocked={privateUnlocked}
                    today={today}
                    onJump={()=>onDay(trackerId,day)}
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
              trackers={trackers}
              privateUnlocked={privateUnlocked}
              today={today}
              onJump={() => {
                const d = touchDetailDay
                setTouchDetailDay(null)
                onDay(trackerId, d)
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
