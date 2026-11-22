import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { garden, gardenOptions, type GardenState } from './api'
import { defaultHistoryFilters } from './historyQuery'
import { instantLabel } from './presentation'

export function GardenHealth({ state, now }: { state: GardenState; now: number }) {
  const [open, setOpen] = useState(false)
  const [cursors, setCursors] = useState<string[]>([])
  const dates = defaultHistoryFilters()
  const params = new URLSearchParams({ from_day: dates.from_day, to_day: dates.to_day, limit: '12' })
  if (cursors.length) params.set('cursor', cursors.at(-1)!)
  const history = useQuery({ queryKey: ['migarden', 'health', params.toString()], queryFn: ({ signal }) => garden.health(params, signal), enabled: open, ...gardenOptions })
  const health = state.health
  const sample = health?.sample
  return <Card className="min-w-0" data-testid="garden-health">
    <CardHeader><h3 className="text-xl font-extrabold">Sức khỏe ESP32</h3></CardHeader>
    <CardContent className="space-y-3 text-sm">
      <p>Báo cáo xác thực cuối: {state.last_seen_at ? instantLabel(state.last_seen_at) : 'Chưa có'}</p>
      {sample && health ? <>
        <p>Mẫu health nhận {instantLabel(health.received_at)} · {Math.max(0, Math.floor((now - Date.parse(health.received_at)) / 60_000))} phút trước</p>
        <dl className="grid min-w-0 grid-cols-2 gap-3">
          {Object.entries({ Build: sample.build_id, 'Uptime lúc lấy mẫu': `${Math.floor(sample.uptime_seconds / 3600)} giờ ${Math.floor(sample.uptime_seconds % 3600 / 60)} phút`, 'Mã lý do reset': sample.reset_reason ?? 'Chưa rõ', 'Heap trống / thấp nhất': `${sample.free_heap} / ${sample.minimum_heap} byte`, 'Kết nối / đồng bộ': `${sample.wifi_phase} / ${sample.sync_status}`, 'Báo cáo chờ / dấu thiếu': `${sample.pending_reports} / ${sample.evidence_gaps}` }).map(([key, value]) => <div key={key} className="min-w-0 border-b border-border pb-1"><dt className="text-muted-foreground">{key}</dt><dd className="break-all">{value}</dd></div>)}
        </dl>
        <p>Giờ lấy mẫu trên bo: {sample.sampled_at && sample.time_quality !== 'unknown' ? instantLabel(sample.sampled_at) : 'Chưa rõ'} · {sample.time_quality}</p>
      </> : <p>Chưa có dữ liệu sức khỏe. Firmware cũ vẫn dùng chức năng hiện có.</p>}
      <p className="text-muted-foreground">Mẫu thưa có thể bỏ sót sự cố. Khoảng thiếu quan sát chưa xác định nguyên nhân; health không xác nhận đầu ra hay cho phép mở van.</p>
      <Button variant="outline" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? 'Ẩn chi tiết sức khỏe' : 'Xem 7 ngày sức khỏe'}</Button>
      {open && <section aria-label="Lịch sử sức khỏe" className="space-y-2">
        {history.isPending && <p role="status">Đang tải mẫu và mốc boot…</p>}
        {history.isError && <p role="alert">Chưa đọc được lịch sử sức khỏe.</p>}
        <ul className="space-y-2">{history.data?.items.map(item => <li key={item.received_at} className="rounded-lg border border-border p-2">Server nhận {instantLabel(item.received_at)}<br />Uptime {item.sample.uptime_seconds} giây · Chờ {item.sample.pending_reports} báo cáo<br />Giờ bo: {item.sample.sampled_at && item.sample.time_quality !== 'unknown' ? instantLabel(item.sample.sampled_at) : 'Chưa rõ'}</li>)}</ul>
        <p className="font-bold">Mốc server thấy boot (có thể thiếu lý do reset)</p>
        <ul>{history.data?.boots.map(boot => <li key={boot.boot_id}>{instantLabel(boot.first_seen_at)} · Boot {boot.boot_id.slice(0, 8)}</li>)}</ul>
        <div className="flex flex-wrap gap-2"><Button variant="outline" disabled={!cursors.length} onClick={() => setCursors(old => old.slice(0, -1))}>Mẫu mới hơn</Button><Button variant="outline" disabled={!history.data?.next_cursor} onClick={() => setCursors(old => [...old, history.data!.next_cursor!])}>Mẫu cũ hơn</Button></div>
      </section>}
    </CardContent>
  </Card>
}
