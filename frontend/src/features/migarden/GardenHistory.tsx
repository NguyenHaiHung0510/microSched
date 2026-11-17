import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { garden, gardenOptions, type HistoryItem } from './api'
import { duration, explainReason, historyLabel, instantLabel, sources, statusLabels, timeLabel } from './presentation'

const results: Record<string, string> = {
  completed: 'Đã kết thúc', stopped: 'Đã dừng theo báo cáo', stop_processed: 'Xử lý Dừng',
  fault: 'Có lỗi', unknown: 'Chưa rõ', rejected: 'Từ chối', skipped: 'Bỏ qua', started: 'Đã bắt đầu',
}

function HistoryList({ items, compact }: { items: HistoryItem[]; compact: boolean }) {
  if (items.length === 0) return <p className="text-sm text-muted-foreground">Chưa nhận được sự kiện phù hợp.</p>
  return <ul className="divide-y divide-muted">
    {items.map(item => {
      const at = item.occurred_at && item.time_quality !== 'unknown' ? item.occurred_at : null
      const source = item.source ? sources[item.source] : 'Chưa rõ nguồn'
      return <li key={item.id} className="grid min-w-0 gap-1 py-2 sm:grid-cols-[auto_minmax(0,1fr)] sm:gap-3">
        <div className="text-sm font-bold tabular-nums">{at
          ? <time dateTime={at}>{compact ? timeLabel(at) : instantLabel(at)}</time> : 'Chưa rõ giờ'}</div>
        <div className="min-w-0 break-words">
          <p className="font-bold">{historyLabel(item)} · {source}</p>
          <p className="text-sm text-muted-foreground">
            {item.result && (statusLabels[item.result] ?? item.result)}
            {item.duration_seconds !== null && ' · ' + duration(item.duration_seconds)}
            {item.kind === 'session_ended' && item.duration_seconds === null && ' · Không đủ dữ liệu thời lượng'}
          </p>
          {!compact && <div className="mt-1 space-y-0.5 text-sm">
            {item.scheduled_at && <p>Kỳ dự kiến: {instantLabel(item.scheduled_at)}</p>}
            {item.received_at && <p>Web nhận: {instantLabel(item.received_at)}</p>}
            {item.planned_duration_seconds !== null && <p>Thời lượng đã chốt: {duration(item.planned_duration_seconds)}</p>}
            {item.config_ref && (item.config_known
              ? <p className="break-all text-muted-foreground">Bản cấu hình: {item.config_ref}</p>
              : <p>Thiếu bản cấu hình gốc.</p>)}
            {item.reason && <p className="break-words">{explainReason(item.reason)}</p>}
          </div>}
        </div>
      </li>
    })}
  </ul>
}

export function GardenHistory({ compact, onNavigate }: { compact: boolean; onNavigate: () => void }) {
  const [filters, setFilters] = useState({ from_day: '', to_day: '', source: 'all', result: 'all' })
  const [cursors, setCursors] = useState<string[]>([])
  const params = new URLSearchParams({ limit: compact ? '4' : '20' })
  for (const [key, value] of Object.entries(filters)) if (value && value !== 'all') params.set(key, value)
  if (cursors.length) params.set('cursor', cursors[cursors.length - 1])
  const badRange = !!(filters.from_day && filters.to_day && filters.from_day > filters.to_day)
  const query = useQuery({
    queryKey: ['migarden', 'history', params.toString()],
    queryFn: ({ signal }) => garden.history(params, signal),
    ...gardenOptions, enabled: !badRange,
    refetchInterval: q => q.state.status === 'error' ? 60_000 : 15_000,
  })
  function update(key: keyof typeof filters, value: string) {
    setFilters(old => ({ ...old, [key]: value }))
    setCursors([])
  }
  return <Card data-testid={compact ? 'garden-recent' : 'garden-history'} className="min-w-0">
    <CardHeader className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="text-xl font-extrabold">{compact ? 'Gần đây' : 'Lịch sử Khu A'}</h3>
      <Button type="button" variant="ghost" className="min-h-11 text-primary" onClick={onNavigate}>
        {!compact && <ArrowLeft aria-hidden="true" />}{compact ? 'Xem lịch sử' : 'Về Tổng quan'}
      </Button>
    </CardHeader>
    <CardContent className="space-y-3">
      {!compact && <div className="grid items-end gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {(['from_day', 'to_day'] as const).map((key, index) => <label htmlFor={'garden-' + key} key={key} className="grid min-w-0 gap-1">
          {index === 0 ? 'Từ ngày' : 'Đến ngày'}<Input id={'garden-' + key} type="date" className="min-h-11 w-full text-base"
            value={filters[key]} onChange={e => update(key, e.target.value)} />
        </label>)}
        {(['source', 'result'] as const).map((key, index) => <div className="grid min-w-0 gap-1" key={key}>
          <label htmlFor={'garden-' + key}>{index === 0 ? 'Nguồn' : 'Kết quả'}</label>
          <Select value={filters[key]} onValueChange={value => update(key, value)}>
            <SelectTrigger id={'garden-' + key} className="w-full text-base" size="lg"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tất cả</SelectItem>
              {Object.entries(key === 'source' ? sources : results).map(([value, label]) =>
                <SelectItem key={value} value={value}>{label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>)}
      </div>}
      {badRange && <p role="alert">Ngày kết thúc phải từ ngày bắt đầu trở đi.</p>}
      {!badRange && query.isPending && <p role="status">Đang tải lịch sử…</p>}
      {query.isError && <div role="alert" className="flex flex-wrap items-center gap-2">
        <p>Không cập nhật được lịch sử.</p>
        <Button type="button" variant="outline" onClick={() => void query.refetch()}>Thử lại</Button>
      </div>}
      {query.data && <HistoryList items={query.data.items} compact={compact} />}
      {!compact && <>
        <p className="text-sm text-muted-foreground">Giờ Hà Nội. Hiển thị phần đã nhận; thiếu báo cáo không chứng minh đã hay chưa tưới.</p>
        <div className="flex flex-wrap justify-between gap-2">
          <Button type="button" variant="outline" disabled={!cursors.length} className="min-h-11" onClick={() => setCursors(old => old.slice(0, -1))}>
            <ChevronLeft aria-hidden="true" /> Trang trước
          </Button>
          <Button type="button" variant="outline" disabled={!query.data?.next_cursor} className="min-h-11"
            onClick={() => { if (query.data?.next_cursor) setCursors(old => [...old, query.data.next_cursor!]) }}>
            Trang sau <ChevronRight aria-hidden="true" />
          </Button>
        </div>
      </>}
    </CardContent>
  </Card>
}
