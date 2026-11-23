import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { garden, gardenOptions, gardenKey, type DailyPoint } from './api'
import { dayLabel, duration } from './presentation'
import { humanActive } from '@/human-activity'

const series = [
  { key: 'schedule_seconds', label: 'Theo lịch', cls: 'garden-schedule' },
  { key: 'remote_seconds', label: 'Từ web', cls: 'garden-remote' },
  { key: 'local_button_seconds', label: 'Tại nút', cls: 'garden-local' },
] as const
function total(point: DailyPoint) {
  return series.reduce((sum, source) => sum + (point[source.key] ?? 0), 0)
}

export function WaterChart() {
  const [days, setDays] = useState<7 | 30>(7)
  const [selected, choose] = useState<string | null>(null)
  const [table, setTable] = useState(false)
  const daily = useQuery({
    queryKey: gardenKey('daily', days), queryFn: ({ signal }) => garden.daily(days, signal),
    ...gardenOptions, refetchInterval: query => !humanActive() ? false : query.state.status === 'error' ? 60_000 : 30_000,
  })
  const projection = daily.data?.schedule_projection
  const forecast = projection ? projection.possible_previous_run ? projection.last_confirmed : projection.saved : daily.data?.forecast
  const possible = projection?.possible_previous_run
  const hasForecast = forecast?.status === 'scheduled' && forecast.day !== null
  const points = daily.data?.days ?? []
  const maxMinutes = Math.max(15, Math.ceil(Math.max(0, ...points.map(total), forecast?.day_total_seconds ?? 0) / 300) * 5)
  const columns = points.length + (hasForecast ? 1 : 0)
  const picked = points.find(point => point.day === selected)
  return <Card data-testid="migarden-chart" className="min-w-0">
    <CardHeader className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="text-xl font-extrabold">Phút tưới theo ngày</h3>
      <div className="flex gap-2" aria-label="Khoảng biểu đồ">
        {([7, 30] as const).map(count => <Button key={count} type="button" aria-pressed={days === count}
          variant={days === count ? 'selected' : 'outline'} className="min-h-11"
          onClick={() => { setDays(count); choose(null) }}>{count} ngày</Button>)}
      </div>
    </CardHeader>
    <CardContent className="space-y-3">
      {daily.isPending && <p role="status">Đang tải biểu đồ…</p>}
      {daily.isError && <div role="alert" className="flex flex-wrap items-center gap-2">
        <p>Không cập nhật được biểu đồ.</p>
        <Button type="button" variant="outline" onClick={() => void daily.refetch()}>Thử lại</Button>
      </div>}
      {daily.data && <>
        <div className="flex gap-2" aria-label={'Biểu đồ ' + days + ' ngày theo giờ Hà Nội'}>
          <div className="garden-chart-axis" aria-hidden="true">
            <span>{maxMinutes} phút</span><span>{Math.round(maxMinutes / 2)}</span><span>0</span>
          </div>
          <div className="min-w-0 flex-1 overflow-x-auto">
          <div className="garden-chart-columns" style={{ gridTemplateColumns: 'repeat(' + columns + ', minmax(0, 1fr))', minWidth: days === 30 ? 25 * columns : undefined }}>
            {points.map((point, index) => {
              const label = dayLabel(point.day)
              const known = point.coverage === 'partial'
              const title = label + ': ' + (known ? duration(total(point)) + ' đã báo, có thể còn thiếu' : 'Thiếu dữ liệu')
              return <div className="flex min-w-0 flex-col items-center" key={point.day}>
                <Button type="button" variant="ghost" aria-label={title} title={title}
                  className={cn('garden-bar w-full min-w-0 rounded-sm px-0', selected === point.day && 'bg-accent/60')}
                  aria-pressed={selected === point.day} onClick={() => choose(point.day)}>
                  <span className="flex w-[75%] flex-col-reverse overflow-hidden rounded-t-sm" aria-hidden="true">
                    {series.map(source => point[source.key] ? <span key={source.key}
                      className={source.cls} style={{ height: 'calc(var(--garden-chart-height) * ' + (point[source.key]! / (maxMinutes * 60)) + ')' }} /> : null)}
                    {!known && <span className="garden-missing" />}
                    {known && total(point) === 0 && <span className="garden-zero" />}
                  </span>
                </Button>
                {(days === 7 || index % 7 === 0 || index === points.length - 1) &&
                  <span aria-hidden="true" className="text-xs tabular-nums">{label}</span>}
              </div>
            })}
            {hasForecast && <div className="flex min-w-0 flex-col items-center border-l border-dashed border-border">
              <Button type="button" variant="ghost" className="garden-bar w-full min-w-0 px-0" aria-pressed={selected === 'forecast'}
                aria-label={'Dự kiến ' + dayLabel(forecast!.day!) + ': ' + duration(forecast!.day_total_seconds!)} onClick={() => choose('forecast')}>
                <span className="garden-forecast w-[75%] rounded-t-sm" aria-hidden="true"
                  style={{ height: 'calc(var(--garden-chart-height) * ' + (forecast!.day_total_seconds! / (maxMinutes * 60)) + ')' }} />
              </Button>
              <span className="text-xs tabular-nums" aria-hidden="true">{dayLabel(forecast!.day!)}</span>
            </div>}
          </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm">
          {series.map(source => <span key={source.key} className="inline-flex items-center gap-1.5">
            <i className={cn('size-3 rounded-sm', source.cls)} aria-hidden="true" />{source.label}
          </span>)}
          <span className="inline-flex items-center gap-1.5"><i className="garden-forecast size-3 rounded-sm" aria-hidden="true" />{possible ? 'Có thể chạy theo bản trước' : 'Dự kiến'}</span>
          <span className="inline-flex items-center gap-1.5"><i className="garden-missing size-3 rounded-sm" aria-hidden="true" />Thiếu dữ liệu</span>
        </div>
        {picked && <p role="status" className="rounded-lg bg-muted p-2 text-sm">
          {dayLabel(picked.day)} · {picked.coverage === 'unknown' ? 'Chưa đủ dữ liệu' :
            series.map(source => source.label + ': ' + (picked[source.key] == null ? 'chưa rõ' : duration(picked[source.key]!))).join(' · ')}
        </p>}
        {selected === 'forecast' && hasForecast && <p role="status" className="rounded-lg bg-accent p-2 text-sm">
          {dayLabel(forecast!.day!)} · {duration(forecast!.day_total_seconds!)} {possible ? 'có thể vẫn chạy theo bản ESP xác nhận trước; bản mới chưa được xác nhận.' : 'theo bản đã lưu. Tới giờ, Controller vẫn kiểm giới hạn.'}
        </p>}
        <p className="text-sm text-muted-foreground">Thời gian đầu ra từ các lượt đã kết thúc được báo về. Có thể còn thiếu báo cáo.</p>
        <Button type="button" className="min-h-11" variant="ghost" aria-expanded={table} onClick={() => setTable(!table)}>
          {table ? 'Ẩn số liệu theo ngày' : 'Xem số liệu theo ngày'}
        </Button>
        {table && <ul className="grid gap-2 text-sm sm:grid-cols-2">
          {points.map(point => <li key={point.day} className="rounded border border-muted bg-background p-2">
            <time dateTime={point.day} className="font-bold">{dayLabel(point.day)}</time>{' · '}
            {point.coverage === 'unknown' ? 'Thiếu dữ liệu' : series.filter(source => point[source.key] !== null)
              .map(source => source.label + ': ' + duration(point[source.key]!)).join(' · ') + ' (đã nhận)'}
          </li>)}
        </ul>}
      </>}
    </CardContent>
  </Card>
}
