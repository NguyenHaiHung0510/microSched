import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarDays, Check, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, Filter, Hand, Laptop, Square } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { garden, gardenOptions, type Command, type HistoryItem, type TimelineItem } from './api'
import { historyPoll, type GardenTimelineModel } from './historyQuery'
import { duration, explainReason, historyLabel, instantLabel, reconcileRecent, sources, statusLabels, timeLabel } from './presentation'

const results: Record<string, string> = {
  completed: 'Hoàn tất', stopped: 'Đã dừng', stop_processed: 'Xử lý Dừng',
  fault: 'Có lỗi', unknown: 'Chưa rõ', rejected: 'Từ chối', skipped: 'Bỏ qua', started: 'Đã báo bắt đầu',
  recovered: 'Đã đối soát',
}
const sourceIcons = { schedule: CalendarDays, remote: Laptop, local_button: Hand }
const scheduleEdits = new Set(['schedule_saved', 'schedule_changed', 'schedule_paused', 'schedule_resumed'])
const configReports = new Set(['config_applied', 'config_rejected'])
const preciseTime = new Intl.DateTimeFormat('vi-VN', {
  timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
})

const eventTime = (item: HistoryItem) => item.time_quality === 'unknown' ? null : item.occurred_at

function resultLabel(item: TimelineItem) {
  if (scheduleEdits.has(item.kind)) return 'Đã lưu'
  if (item.kind === 'config_applied') return 'ESP xác nhận'
  if (item.kind === 'remote_stop' || item.kind === 'stop_processed') {
    const result = item.evidence.find(event => event.kind === 'stop_processed')?.result ?? item.result
    if (result === 'already_off') return 'Dừng khi đầu ra đã tắt'
    if (result === 'close_requested') return 'Đã yêu cầu tắt đầu ra'
  }
  if (item.kind === 'session' && item.result === 'stopped') {
    if (item.reason?.toLowerCase() === 'remote_stop') return 'Dừng từ web'
    if (['local_stop', 'stopped'].includes(item.reason?.toLowerCase() ?? '')) return 'Dừng tại nút'
  }
  if (item.kind === 'session' && item.result === 'unknown' && item.duration_seconds === null) return 'Chưa rõ thời lượng'
  return item.result ? results[item.result] ?? statusLabels[item.result] ?? item.result : 'Chưa rõ'
}

function SourceLabel({ source, kind }: Pick<HistoryItem, 'source' | 'kind'>) {
  if (scheduleEdits.has(kind)) return <span>Web</span>
  if (configReports.has(kind)) return <span>ESP32</span>
  const Icon = source ? sourceIcons[source] : CircleHelp
  return <span className="inline-flex items-center gap-1.5"><Icon className="size-4 shrink-0 text-primary" aria-hidden="true" />{source ? sources[source] : 'Chưa rõ nguồn'}</span>
}

function ResultLabel({ item }: { item: TimelineItem }) {
  const success = item.result === 'completed' || item.kind === 'config_applied' || scheduleEdits.has(item.kind)
  const stopped = item.result === 'stopped' || item.kind === 'remote_stop' || item.kind === 'stop_processed'
  const Icon = success ? Check : stopped ? Square : CircleHelp
  return <Badge variant="secondary" className={cn('h-auto max-w-full whitespace-normal px-2 py-1', success && 'bg-ok-bg text-ok', stopped && 'bg-bad-bg text-bad')}>
    <Icon aria-hidden="true" />{resultLabel(item)}
  </Badge>
}

function Moment({ at }: { at: string | null }) {
  return at ? <time className="tabular-nums" dateTime={at}>
    <span className="font-semibold">{preciseTime.format(new Date(at))}</span>{' '}
    <span className="text-xs text-muted-foreground">{instantLabel(at).split(' · ')[0]}</span>
  </time> : <span className="text-muted-foreground">—</span>
}

function TimelineMoment({ item }: { item: TimelineItem }) {
  const occurred = eventTime(item)
  return configReports.has(item.kind) && !occurred && item.received_at
    ? <><span className="mr-1 text-xs text-muted-foreground">Server nhận</span><Moment at={item.received_at} /></>
    : <Moment at={occurred} />
}

function TimelineDetails({ item }: { item: TimelineItem }) {
  return <div className="space-y-3 text-sm">
    {item.kind === 'session' && <dl className="grid grid-cols-2 gap-2">
      <dt>Bắt đầu</dt><dd><Moment at={item.started_at} /></dd>
      <dt>Kết thúc</dt><dd><Moment at={item.ended_at} /></dd>
      <dt>Thời lượng đã báo</dt><dd>{item.duration_seconds === null ? 'Chưa rõ' : duration(item.duration_seconds)}</dd>
    </dl>}
    {item.planned_duration_seconds !== null && <p>Dự kiến: {duration(item.planned_duration_seconds)}</p>}
    {item.config_ref && <p className="break-all text-muted-foreground">
      {item.config_known ? 'Bản cấu hình: ' + item.config_ref : 'Thiếu bản cấu hình gốc.'}
    </p>}
    {(item.kind === 'session' ? item.evidence : [item, ...item.evidence]).map(event => <div className="rounded-lg border border-border p-3" key={event.id}>
      <p className="font-bold">{historyLabel(event)}</p>
      <p>{eventTime(event) ? instantLabel(eventTime(event)!) : 'Chưa rõ giờ nguồn'}</p>
      {event.received_at && <p className="text-muted-foreground">Web nhận: {instantLabel(event.received_at)}</p>}
      {event.result && <p>{event.result === 'applied' ? 'ESP xác nhận' : statusLabels[event.result] ?? results[event.result] ?? event.result}</p>}
      {event.reason && <p className="break-words">{explainReason(event.reason)}</p>}
    </div>)}
    {item.reason && item.kind === 'session' && <p className="break-words">{explainReason(item.reason)}</p>}
    <p className="text-muted-foreground">Đây là thời gian và trạng thái do Controller báo; không đo lượng nước.</p>
  </div>
}

export function GardenRecent({ onNavigate, currentRequests }: {
  onNavigate: () => void; currentRequests: (Command | null)[];
}) {
  const query = useQuery({
    queryKey: ['migarden', 'history', 'limit=4'],
    queryFn: ({ signal }) => garden.history(new URLSearchParams({ limit: '4' }), signal),
    ...gardenOptions, refetchInterval: historyPoll,
  })
  const items = reconcileRecent(query.data?.items ?? [], currentRequests)
  return <Card data-testid="garden-recent" className="min-w-0">
    <CardHeader className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="text-xl font-extrabold">Gần đây</h3>
      <Button type="button" variant="ghost" className="min-h-11 text-primary" onClick={onNavigate}>Xem lịch sử</Button>
    </CardHeader>
    <CardContent>
      {query.isPending && <p role="status">Đang tải lịch sử…</p>}
      {query.isError && <p role="alert">Không cập nhật được lịch sử.</p>}
      {query.data && !items.length && <p className="text-sm text-muted-foreground">Chưa nhận được sự kiện phù hợp.</p>}
      <ul className="divide-y divide-muted">{items.map(item => <li key={item.id} className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)] gap-2 py-2">
        <p className="text-sm font-bold tabular-nums">{eventTime(item) ? timeLabel(eventTime(item)!) : 'Chưa rõ giờ'}</p>
        <div className="min-w-0 break-words">
          <p className="font-bold">{historyLabel(item)} · {item.source ? sources[item.source] : 'Chưa rõ nguồn'}</p>
          <p className="text-sm text-muted-foreground">
            {item.result && (statusLabels[item.result] ?? item.result)}
            {item.duration_seconds !== null && ' · ' + duration(item.duration_seconds)}
            {item.kind === 'session_ended' && item.duration_seconds === null && ' · Không đủ dữ liệu thời lượng'}
          </p>
        </div>
      </li>)}</ul>
    </CardContent>
  </Card>
}
export function GardenHistory({ timeline, onVersion }: { timeline: GardenTimelineModel; onVersion: (ref: string) => void }) {
  const { filters, query, update, badRange } = timeline
  const [filterOpen, setFilterOpen] = useState(false)
  const [selected, setSelected] = useState<TimelineItem | null>(null)
  const opener = useRef<HTMLButtonElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const items = query.data?.items ?? []
  const totals = query.data?.totals
  const detail = items.find(item => item.id === selected?.id) ?? selected
  const openDetail = (item: TimelineItem, button: HTMLButtonElement) => { opener.current = button; setSelected(item) }
  return <Card data-testid="garden-history" className="min-w-0">
    <CardHeader className="flex flex-wrap items-start justify-between gap-2">
      <h3 className="flex items-center gap-2 text-xl font-extrabold" ref={heading} tabIndex={-1}>
        <CalendarDays aria-hidden="true" className="size-5 text-primary" />Lịch sử tưới
      </h3>
      <Button variant="outline" onClick={() => { document.getElementById('garden-versions')?.scrollIntoView({ block: 'start' }); document.querySelector<HTMLElement>('#garden-versions h3')?.focus({ preventScroll: true }) }}>Phiên bản lịch</Button>
      {query.data && <div className="space-y-1 text-sm">
        {totals && totals.recorded_seconds !== null ? <>
          <p><strong>{duration(totals.recorded_seconds)}</strong> đã ghi nhận</p>
          <p className="flex flex-wrap gap-x-3 text-muted-foreground">
            {([['schedule_seconds', 'Theo lịch'], ['remote_seconds', 'Từ web'], ['local_button_seconds', 'Tại nút']] as const).map(([key, label]) =>
              totals[key] === null ? null : <span key={key}>{label}: {duration(totals[key]!)}</span>)}
          </p>
        </> : <p className="text-muted-foreground">{totals ? 'Chưa có thời lượng đã báo trong khoảng lọc.' : 'Không có tổng cho bộ lọc này. Chọn khoảng đến 31 ngày để xem tổng đã báo.'}</p>}
      </div>}
    </CardHeader>
    <CardContent className="space-y-3">
      <div className="flex flex-wrap items-center gap-2"><p className="text-sm text-muted-foreground">Mặc định 7 ngày gần nhất · Giờ Hà Nội</p><Select value={filters.category} onValueChange={value => update('category', value)}><SelectTrigger aria-label="Loại sự kiện" className="min-h-11 w-auto"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Tất cả sự kiện</SelectItem><SelectItem value="watering">Tưới</SelectItem><SelectItem value="configuration">Thay đổi lịch</SelectItem></SelectContent></Select></div>
      <Button type="button" variant="outline" className="min-h-11 w-full justify-between lg:hidden" aria-expanded={filterOpen}
        aria-controls="garden-history-filters" onClick={() => setFilterOpen(!filterOpen)}>
        <span className="flex items-center gap-2"><Filter aria-hidden="true" />Bộ lọc</span><ChevronDown aria-hidden="true" />
      </Button>
      <div id="garden-history-filters" className={cn('grid-cols-1 gap-3 sm:grid-cols-2 lg:grid lg:grid-cols-4', filterOpen ? 'grid' : 'hidden')}>
        {([['from_day', 'Từ ngày'], ['to_day', 'Đến ngày']] as const).map(([key, label]) => <label htmlFor={'garden-' + key} key={key} className="grid min-w-0 gap-1 text-sm">
          {label}<Input id={'garden-' + key} type="date" className="min-h-11 w-full text-base"
            value={filters[key]} onChange={event => update(key, event.target.value)} />
        </label>)}
        {([['source', 'Nguồn'], ['result', 'Kết quả']] as const).map(([key, label]) => <div className="grid min-w-0 gap-1 text-sm" key={key}>
          <label htmlFor={'garden-' + key}>{label}</label>
          <Select value={filters[key]} onValueChange={value => update(key, value)}>
            <SelectTrigger id={'garden-' + key} className="w-full text-base" size="lg"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tất cả</SelectItem>
              {Object.entries(key === 'source' ? sources : results).map(([value, text]) => <SelectItem key={value} value={value}>{text}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>)}
        <Button type="button" variant="ghost" className="min-h-11 w-fit px-0" onClick={timeline.allDates}>Mọi ngày, kể cả ngày chưa rõ</Button>
      </div>
      {badRange && <p role="alert">Ngày kết thúc phải từ ngày bắt đầu trở đi.</p>}
      {!badRange && query.isPending && <p role="status">Đang tải lịch sử…</p>}
      {query.isError && <div role="alert" className="flex flex-wrap items-center gap-2">
        <p>Không cập nhật được lịch sử.</p><Button type="button" variant="outline" onClick={() => void query.refetch()}>Thử lại</Button>
      </div>}
      {query.data && !items.length && <p>Chưa nhận được sự kiện phù hợp.</p>}
      {items.length > 0 && <>
        <div className="hidden overflow-x-auto rounded-xl border border-border lg:block">
          <table className="w-full text-left text-sm" aria-label="Lịch sử tưới">
            <thead className="bg-muted"><tr>
              {['Bắt đầu', 'Kết thúc', 'Nguồn', 'Thời lượng đã báo', 'Kết quả', 'Chi tiết'].map(label => <th key={label} scope="col" className="px-3 py-2.5">{label}</th>)}
            </tr></thead>
            <tbody className="divide-y divide-border">{items.map(item => <tr key={item.id} className="align-middle">
              {item.kind === 'session' ? <>
                <td className="px-3 py-2"><Moment at={item.started_at} /></td>
                <td className="px-3 py-2"><Moment at={item.ended_at} /></td>
              </> : <td colSpan={2} className="px-3 py-2"><span className="mr-2 font-semibold">{historyLabel(item)}</span><TimelineMoment item={item} /></td>}
              <td className="px-3 py-2"><SourceLabel source={item.source} kind={item.kind} /></td>
              <td className="px-3 py-2">{item.duration_seconds === null ? '—' : duration(item.duration_seconds)}</td>
              <td className="px-3 py-2"><ResultLabel item={item} /></td>
              <td className="px-3 py-2"><Button type="button" variant="ghost" className="min-h-11" onClick={e => openDetail(item, e.currentTarget)}>Chi tiết</Button>{item.config_ref && item.config_known && <Button variant="outline" className="min-h-11" onClick={() => onVersion(item.config_ref!)}>Xem phiên bản</Button>}</td>
            </tr>)}</tbody>
          </table>
        </div>
        <ul className="space-y-2 lg:hidden" aria-label="Lịch sử tưới">{items.map(item => <li key={item.id} className="rounded-xl border border-border">
          <Button type="button" variant="ghost" className="h-auto min-h-11 w-full flex-wrap justify-between gap-2 whitespace-normal px-3 py-2 text-left"
            onClick={e => openDetail(item, e.currentTarget)}>
            <span className="min-w-0 space-y-1">
              <span className="block font-bold">
                {item.kind === 'session' ? <><Moment at={item.started_at} /> – <Moment at={item.ended_at} /></> : <>{historyLabel(item)} · <TimelineMoment item={item} /></>}
              </span>
              <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <SourceLabel source={item.source} kind={item.kind} /> · {item.duration_seconds === null ? '—' : duration(item.duration_seconds)}
              </span>
            </span>
            <span className="flex min-w-0 items-center gap-1"><ResultLabel item={item} /><ChevronRight aria-hidden="true" className="shrink-0" /></span>
          </Button>
          {item.config_ref && item.config_known && <Button variant="outline" className="mb-2 ml-3 min-h-11" onClick={() => onVersion(item.config_ref!)}>Xem phiên bản</Button>}
        </li>)}</ul>
      </>}
      <p className="text-sm text-muted-foreground">Giờ Hà Nội. Tổng là thời lượng đã ghi nhận của các lượt kết thúc trong khoảng lọc, trên mọi trang; thiếu báo cáo không chứng minh đã hay chưa tưới.</p>
      <div className="flex justify-between gap-2">
        <Button type="button" variant="outline" className="min-h-11" disabled={!timeline.newer} onClick={timeline.newer}>
          <ChevronLeft aria-hidden="true" />Mới hơn
        </Button>
        <Button type="button" variant="outline" className="min-h-11" disabled={!timeline.older} onClick={timeline.older}>
          Cũ hơn<ChevronRight aria-hidden="true" />
        </Button>
      </div>
      <Dialog open={detail !== null} onOpenChange={open => { if (!open) setSelected(null) }}>
        <DialogContent className="max-h-[85dvh] overflow-y-auto" onCloseAutoFocus={event => {
          event.preventDefault()
          if (opener.current?.isConnected) opener.current.focus()
          else heading.current?.focus()
        }}>
          <DialogHeader><DialogTitle>{detail?.kind === 'session' ? 'Chi tiết lượt tưới' : detail && historyLabel(detail)}</DialogTitle>
            <DialogDescription>{detail && resultLabel(detail)} · Khu A</DialogDescription></DialogHeader>
          {detail && <TimelineDetails item={detail} />}
          {detail?.config_ref && detail.config_known && <Button variant="outline" onClick={() => { setSelected(null); onVersion(detail.config_ref!) }}>Xem phiên bản</Button>}
        </DialogContent>
      </Dialog>
    </CardContent>
  </Card>
}
