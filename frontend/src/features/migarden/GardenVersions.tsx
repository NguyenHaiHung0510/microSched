import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { garden, gardenOptions, type Bundle } from './api'
import { duration, explainReason, instantLabel, scheduleLabel } from './presentation'

function contentRows(bundle: Bundle): Record<string, string> {
  return {
    'Lịch': scheduleLabel(bundle.schedule),
    'Hiệu lực từ': instantLabel(bundle.schedule.effective_from),
    'Hiệu lực đến': bundle.schedule.effective_until ? instantLabel(bundle.schedule.effective_until) : 'Không đặt',
    'Nút START': duration(bundle.policy.manual_duration_seconds),
    'Tối đa mỗi lượt': duration(bundle.policy.max_session_seconds),
    'Tổng tối đa trong 3 giờ': duration(bundle.policy.max_window_seconds),
  }
}

export function GardenVersions({ selected, onSelect }: { selected: string | null; onSelect: (ref: string) => void }) {
  const [cursors, setCursors] = useState<string[]>([])
  const heading = useRef<HTMLHeadingElement>(null)
  const params = new URLSearchParams({ limit: '10' })
  if (cursors.length) params.set('cursor', cursors.at(-1)!)
  const versions = useQuery({ queryKey: ['migarden', 'versions', params.toString()], queryFn: ({ signal }) => garden.versions(params, signal), ...gardenOptions })
  const detail = useQuery({ queryKey: ['migarden', 'version', selected], queryFn: ({ signal }) => garden.version(selected!, signal), enabled: !!selected, ...gardenOptions })
  useEffect(() => { if (selected) { heading.current?.scrollIntoView({ block: 'nearest' }); heading.current?.focus({ preventScroll: true }) } }, [selected])
  const data = detail.data
  const fields = data ? contentRows(data.bundle) : {}
  const previous = data?.previous_bundle ? contentRows(data.previous_bundle) : null
  return <Card id="garden-versions" data-testid="garden-versions" className="min-w-0">
    <CardHeader><h3 ref={heading} tabIndex={-1} className="text-xl font-extrabold">Phiên bản lịch</h3><p className="text-sm text-muted-foreground">Mới nhất trước · Chỉ xem, không áp dụng lại lịch</p></CardHeader>
    <CardContent className="space-y-3">
      {versions.isPending && <p role="status">Đang tải phiên bản…</p>}
      {versions.isError && <p role="alert">Chưa đọc được danh sách phiên bản.</p>}
      <ul className="divide-y divide-border">{versions.data?.items.map(version => <li key={version.config_ref} className="space-y-1 py-3">
        <p className="break-all font-bold">Bản {version.config_ref.slice(0, 8)} {version.is_saved && '· Đã lưu gần nhất'} {version.is_last_confirmed && '· ESP xác nhận gần nhất'}</p>
        <p className="text-sm">{scheduleLabel(version.bundle.schedule)}</p>
        <p className="text-sm text-muted-foreground">Lưu {instantLabel(version.saved_at)}</p>
        <Button type="button" variant="outline" className="min-h-11" aria-pressed={selected === version.config_ref} onClick={() => onSelect(version.config_ref)}>Xem phiên bản</Button>
      </li>)}</ul>
      {versions.data?.items.length === 0 && <p>Chưa có phiên bản lịch.</p>}
      <div className="flex flex-wrap justify-between gap-2">
        <Button variant="outline" disabled={!cursors.length} onClick={() => setCursors(old => old.slice(0, -1))}>Mới hơn</Button>
        <Button variant="outline" disabled={!versions.data?.next_cursor} onClick={() => setCursors(old => [...old, versions.data!.next_cursor!])}>Cũ hơn</Button>
      </div>
      {selected && <section aria-label="Chi tiết phiên bản lịch" className="space-y-3 rounded-xl border border-border bg-background p-3">
        {detail.isPending && <p role="status">Đang tải đúng phiên bản…</p>}
        {detail.isError && <p role="alert">Chưa đọc được phiên bản này. Không suy ra đã áp dụng.</p>}
        {data && <>
          <h4 className="break-all font-bold">Bản {data.config_ref}</h4>
          <p className="text-sm">Giờ lưu: {instantLabel(data.saved_at)}</p>
          <p className="break-all text-sm">Bản ESP xác nhận gần nhất: {data.last_confirmed_ref ?? 'Chưa có'}</p>
          <p className="text-sm">{data.schedule_changed ? 'Nội dung so với bản liền trước:' : 'Chỉ đổi policy tại tủ; lịch không đổi.'}</p>
          <dl className="space-y-2 text-sm">{Object.entries(fields).map(([key, value]) => <div key={key} className="min-w-0 border-b border-border pb-1">
            <dt className="font-semibold">{key}</dt><dd className="break-words">{previous && previous[key] !== value && <span className="block text-muted-foreground">Trước: {previous[key]}</span>}{value}</dd>
          </div>)}</dl>
          <h4 className="font-bold">Bằng chứng từ ESP</h4>
          {!data.evidence.length && <p className="text-sm">Chưa có báo cáo áp dụng/từ chối cho bản này. Giờ hiệu lực không phải giờ ESP áp dụng.</p>}
          <ul className="space-y-2 text-sm">{data.evidence.map(event => <li key={event.event_id} className="rounded-lg border border-border p-2">
            <p className="font-semibold">{event.kind === 'config_applied' ? 'ESP xác nhận áp dụng' : 'ESP từ chối'}</p>
            <p>Giờ ESP áp dụng: {event.applied_at ? instantLabel(event.applied_at) : 'Chưa rõ'}</p>
            {event.kind === 'config_applied' && !event.applied_at && event.occurred_at && <p>Giờ bo báo (chưa xác minh) · {instantLabel(event.occurred_at)}</p>}
            <p>Server nhận: {instantLabel(event.received_at)}</p>
            <p>Chất lượng đồng hồ bo báo · {event.time_quality}</p>
            {event.reason && <p>{explainReason(event.reason)}</p>}
          </li>)}</ul>
        </>}
      </section>}
    </CardContent>
  </Card>
}
