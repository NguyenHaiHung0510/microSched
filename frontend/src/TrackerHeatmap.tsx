import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { apiRequest } from '@/api'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { daysInReportMonth } from '@/tracker-rhythm'
import { activityLevel, initialHeatmapMonth, initialRecordsSelection } from '@/tracker-records'
import { standardRefetchInterval } from '@/query-polling'
import { type Tracker } from '@/tracker-ui'

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
export function TrackerHeatmap({ trackers, initialMonth, onDay, privateUnlocked }: { trackers: Tracker[]; initialMonth: string; onDay: (trackerId: string, day: string) => void; privateUnlocked: boolean }) {
  const [yearText,setYearText] = useState(initialMonth.slice(0,4))
  const year = Number(yearText)
  const validYear = /^[0-9]{1,4}$/.test(yearText) && year >= 1 && year <= 9998
  const [month,setMonth] = useState(initialMonth)
  const [trackerId,setTrackerId] = useState('all')
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
      <div className="overflow-x-auto pb-2"><div className="grid min-w-[356px] grid-cols-7 gap-2" data-testid="heatmap-month-grid">
        {WEEKDAYS.map(day=><span key={day} className="py-1 text-center text-xs text-muted-foreground">{day}</span>)}
        {Array.from({length:offset},(_,i)=><span aria-hidden="true" key={`blank-${i}`} />)}
        {days.map(day=>{
          const count=counts.get(day)??0;const level=activityLevel(count);const future=day>today
          return <Button key={day} data-testid="heatmap-day" data-day={day} data-count={count} data-level={level} variant="ghost" className="h-auto min-h-11 min-w-11 flex-col gap-1 p-1" disabled={future} aria-label={`${day}: ${future?'chưa tới':`${count} lần ghi, xem bản ghi`}`} onClick={()=>onDay(trackerId,day)}><span className="text-xs">{Number(day.slice(-2))}</span><span aria-hidden="true" className="size-4 rounded-sm ring-1 ring-border/50" style={{backgroundColor:`var(--heatmap-${level})`}} />{count>0 ? <span className="text-xs tabular-nums">{count}</span> : null}</Button>
        })}
      </div></div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-muted-foreground" aria-label="Thang màu heatmap">
        {LEVELS.map((label,i)=><span key={label} className="inline-flex items-center gap-1"><span aria-hidden="true" className="size-4 rounded-sm ring-1 ring-border/50" style={{backgroundColor:`var(--heatmap-${i})`}} />{label} lần</span>)}<span>Ngày chưa tới: không chọn được</span>
      </div>
      {!counts.size ? <p className="text-sm text-muted-foreground">Chưa có bản ghi trong năm này.</p> : null}
    </>}
  </Card>
}
