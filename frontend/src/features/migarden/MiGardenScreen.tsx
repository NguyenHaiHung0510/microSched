import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { onlineManager, useMutation, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, Droplet, RefreshCw, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { navigate, queryParams } from '@/lib/route'
import { cn } from '@/lib/utils'
import { garden, useGardenState, type Command, type Forecast, type GardenState, type Preview } from './api'
import { Configuration, ConfigStatus } from './Configuration'
import { GardenHistory } from './GardenHistory'
import { WaterChart } from './WaterChart'
import { displayedSession, duration, errorText, explainReason, instantLabel, sources, statusLabels, stopwatch, timeLabel } from './presentation'
import './garden.css'

function NextSchedule({ next, fresh }: { next: Forecast; fresh: boolean }) {
  const empty = {
    no_applied_config: 'Chưa có lịch được ESP32 xác nhận.',
    paused: 'Lịch đã áp dụng đang tạm dừng.',
    no_future_occurrence: 'Không còn lượt sắp tới trong khoảng hiệu lực.',
    scheduled: '',
  }[next.status]
  return <Card>
    <CardHeader><h3 className="text-xl font-extrabold">Lượt sắp tới</h3></CardHeader>
    <CardContent className="space-y-2">
      {next.next_at && next.duration_seconds !== null
        ? <div className="flex items-center gap-3 rounded-lg bg-accent p-3">
          <CalendarDays className="size-6 shrink-0 text-primary" aria-hidden="true" />
          <div><time className="text-xl font-extrabold tabular-nums" dateTime={next.next_at}>{instantLabel(next.next_at)}</time>
            <p className="text-sm">{duration(next.duration_seconds)} · Theo lịch</p></div>
        </div>
        : <p>{empty}</p>}
      {next.next_at && <p className="text-sm text-muted-foreground">
        {fresh ? 'Dự kiến theo lịch đã áp dụng. Tới giờ, Controller vẫn xét giới hạn.'
          : 'Dự kiến theo bản cuối cùng đã xác nhận; trạng thái hiện tại của Controller chưa rõ.'}
      </p>}
    </CardContent>
  </Card>
}

function RequestStatus({ command }: { command: Command | null }) {
  if (!command) return null
  return <div className="min-w-0">
    <span className="font-bold">{command.kind === 'start' ? 'Yêu cầu tưới' : 'Yêu cầu Dừng'} · </span>
    {statusLabels[command.status] ?? command.status}
    {command.reason && <span className="break-words text-muted-foreground"> · {explainReason(command.reason)}</span>}
  </div>
}

function OverviewStatus({ state, dataAt, now, online, connected, refresh }: {
  state: GardenState; dataAt: number; now: number; online: boolean; connected: boolean; refresh: () => void;
}) {
  const client = useQueryClient()
  const opener = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  const [minutes, setMinutes] = useState('')
  const [preview, setPreview] = useState<{ record: Preview; localExpires: number } | null>(null)
  const [formError, setFormError] = useState('')
  const [startNotice, setStartNotice] = useState('')
  const [stopNotice, setStopNotice] = useState('')
  const device = state.snapshot
  const active = device?.active_session
  const display = displayedSession(state, dataAt, now, connected)
  const max = state.config.applied?.policy.max_session_seconds ?? 0
  const canStart = display.fresh && state.start_block_reason === null && Boolean(max)
  const stopBusy = ['stop_requested', 'stop_received'].includes(state.stop_request?.status ?? '')
  const applyCommand = (key: 'start_request' | 'stop_request', data: Command) => {
    client.setQueryData<GardenState>(['migarden', 'state'], previous => previous ? { ...previous, [key]: data } : previous, { updatedAt: dataAt })
    void client.invalidateQueries({ queryKey: ['migarden'] })
  }
  const getPreview = useMutation({
    mutationFn: garden.preview, retry: false, networkMode: 'always',
    onMutate: () => Date.now(),
    onSuccess: (record, _minutes, at) => {
      setPreview({ record, localExpires: (at ?? Date.now()) + 45_000 })
    },
    onError: error => { setFormError(errorText(error, 'Không lấy được bản xem trước. Kiểm tra kết nối và thử lại.')); refresh() },
  })
  const confirm = useMutation({
    mutationFn: garden.confirm, retry: false, networkMode: 'always',
    onSuccess: data => { applyCommand('start_request', data); setOpen(false); setStartNotice('') },
    onError: error => {
      const detail = 'Chưa xác nhận kết quả gửi. Xem trạng thái trước khi gửi yêu cầu mới.'
      setFormError(errorText(error, detail))
      setStartNotice(errorText(error, detail))
      refresh()
    },
  })
  const stop = useMutation({
    mutationFn: garden.stop, retry: false, networkMode: 'always',
    onSuccess: data => { setStopNotice(''); setStartNotice(''); applyCommand('stop_request', data) },
    onError: error => {
      setStopNotice(errorText(error, 'Chưa xác nhận gửi được Dừng. Kiểm tra tại tủ nếu cần dừng ngay.'))
      refresh()
    },
  })
  const liveAt = display.live && active?.started_at ? timeLabel(active.started_at) : null
  const headline = display.live ? 'Đang tưới'
    : active || device?.output === 'on' ? 'Lần cuối xác nhận đang tưới'
      : !display.fresh ? state.connection === 'unconfigured' ? 'Chưa kết nối Controller'
        : state.connection === 'waiting' ? 'Đang chờ Controller' : 'Chưa rõ trạng thái hiện tại'
        : device?.output === 'off' ? 'Đầu ra đang tắt theo báo cáo' : 'Chưa rõ trạng thái đầu ra'
  return <>
    <div className={cn('rounded-xl border px-4 py-3', display.live ? 'border-primary/25 bg-accent' : 'border-muted bg-background')}
      data-testid="garden-now">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1">
          <p className="flex items-center gap-2 text-base font-extrabold lg:text-lg">
            <Droplet aria-hidden="true" className="size-5 shrink-0 text-primary" />
            {headline}{active && <span className="font-normal">· {sources[active.trigger_source]}</span>}
          </p>
          {active && <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 sm:border-l sm:border-muted sm:pl-4">
            {active.started_at && <span>Bắt đầu {liveAt ?? timeLabel(active.started_at)}</span>}
            <span>{display.live ? 'Đã chạy ' : 'Lần cuối đã báo '}
              <strong className="text-lg tabular-nums text-primary" data-testid="garden-elapsed">
                {stopwatch(display.elapsed)} / {stopwatch(active.duration_seconds)}
              </strong>
            </span>
          </div>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button ref={opener} type="button" variant="outline" className="min-h-11" disabled={!canStart} onClick={() => {
            getPreview.reset(); confirm.reset(); setPreview(null); setFormError('')
            setMinutes(String(Math.min(state.config.applied?.policy.manual_duration_seconds ?? 900, max) / 60))
            setOpen(true)
          }}>Tưới ngay</Button>
          <Button type="button" variant="destructive" className="min-h-11"
            disabled={!online || !state.stop_available || stop.isPending || stopBusy}
            onClick={() => { setOpen(false); setStopNotice(''); stop.mutate() }}>
            <Square aria-hidden="true" /> {stop.isPending ? 'Đang gửi Dừng…' : 'Dừng tưới'}
          </Button>
        </div>
      </div>
      <div className="mt-2 space-y-1 text-sm">
        {state.snapshot_received_at && <p className="text-muted-foreground">
          {display.fresh ? 'Đồng bộ' : 'Báo cáo cuối lúc'} {instantLabel(state.snapshot_received_at)}
        </p>}
        {(!canStart && !display.live) && <p>{!online ? 'Web mất kết nối; không xếp lệnh tưới chờ gửi.' :
          explainReason(state.start_block_reason) ?? (display.fresh ? '' : 'Chờ báo cáo mới trước khi tưới từ web.')}</p>}
        {device?.blocked_reason && !device.ready && <p className="break-words">{explainReason(device.blocked_reason)}</p>}
        {(state.start_request || state.stop_request) && <div role="status" className="space-y-1">
          <RequestStatus command={state.start_request} /><RequestStatus command={state.stop_request} />
        </div>}
        {startNotice && <p role="alert">{startNotice}</p>}
        {stopNotice && <p role="alert">{stopNotice}</p>}
      </div>
    </div>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-h-[85dvh] overflow-y-auto"
        onCloseAutoFocus={event => { event.preventDefault(); opener.current?.focus() }}>
        <DialogHeader><DialogTitle>{preview ? 'Xác nhận tưới Khu A' : 'Tưới ngay · Khu A'}</DialogTitle>
          <DialogDescription>{preview
            ? 'Controller sẽ kiểm tra lại điều kiện tại tủ trước khi bắt đầu.'
            : 'Chọn thời lượng rồi xem trước yêu cầu. Chưa gửi lệnh tưới ở bước này.'}</DialogDescription>
        </DialogHeader>
        {preview ? <>
          <dl className="grid grid-cols-2 gap-2 rounded-lg bg-background p-3">
            <dt>Khu</dt><dd className="font-bold">Khu A</dd>
            <dt>Thời lượng</dt><dd className="font-bold">{duration(preview.record.duration_seconds)}</dd>
            <dt>Còn thời gian xác nhận</dt><dd>{Math.ceil(Math.max(0, preview.localExpires - now) / 1000)} giây</dd>
          </dl>
          {now >= preview.localExpires && <p role="status">Bản xem trước đã hết hạn. Hãy xem trước lại.</p>}
          {!display.fresh && <p role="status">Cần báo cáo mới để xác nhận tưới.</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => { setPreview(null); setFormError('') }} disabled={confirm.isPending}>
              Đổi thời lượng
            </Button>
            <Button type="button" disabled={confirm.isPending || !online || !display.fresh || now >= preview.localExpires}
              onClick={() => { setFormError(''); confirm.mutate(preview.record.preview_id) }}>
              {confirm.isPending ? 'Đang gửi…' : 'Xác nhận tưới'}
            </Button>
          </DialogFooter>
        </> : <form className="space-y-3" onSubmit={event => {
          event.preventDefault()
          const seconds = Number(minutes) * 60
          if (seconds < 15 || seconds > max || seconds % 15 !== 0) { setFormError('Chọn thời lượng hợp lệ, theo bước 15 giây.'); return }
          setFormError(''); getPreview.mutate(seconds)
        }}>
          <label htmlFor="garden-start-duration" className="grid gap-1 text-sm">
            Thời lượng tưới (phút)
            <Input id="garden-start-duration" type="number" value={minutes} min={0.25} max={max / 60} step={0.25} required
              className="min-h-11 text-base" onChange={event => setMinutes(event.target.value)} />
          </label>
          <p className="text-sm text-muted-foreground">Tối đa {duration(max)} mỗi lượt theo bản đã áp dụng.</p>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Hủy</Button>
            <Button type="submit" disabled={!canStart || getPreview.isPending}>{getPreview.isPending ? 'Đang kiểm tra…' : 'Xem trước'}</Button>
          </DialogFooter>
        </form>}
        {formError && <p role="alert" className="rounded-lg bg-bad-bg p-3 text-sm text-bad">{formError}</p>}
      </DialogContent>
    </Dialog>
  </>
}

export function MiGardenScreen({ location }: { location: string }) {
  const route = queryParams(location)
  const configuration = route.get('tab') === 'config'
  const history = !configuration && route.get('history') === '1'
  const [now, setNow] = useState(() => Date.now())
  const online = useSyncExternalStore(onlineManager.subscribe, () => onlineManager.isOnline())
  const state = useGardenState()
  const cache = useQueryClient()
  const data = state.data
  useEffect(() => {
    if (configuration || history) return
    const id = window.setInterval(() => { if (!document.hidden) setNow(Date.now()) }, 1000)
    return () => window.clearInterval(id)
  }, [configuration, history])
  const connected = online && !state.isError
  const fresh = data && displayedSession(data, state.dataUpdatedAt, now, connected).fresh
  const refresh = () => { void state.refetch() }
  return <section aria-labelledby="migarden-title" data-testid="migarden-screen" className="space-y-4">
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex min-w-0 flex-wrap items-start gap-x-6 gap-y-3">
        <div><h2 id="migarden-title" className="text-3xl font-extrabold tracking-tight">miGarden</h2>
          <p className="text-base text-muted-foreground">Khu A</p></div>
        <nav className="flex flex-wrap gap-2" aria-label="Mục trong miGarden">
          <Button variant={configuration ? 'outline' : 'selected'} aria-current={!configuration ? 'page' : undefined}
            className="min-h-11" onClick={() => navigate('/migarden')}>Tổng quan</Button>
          <Button variant={configuration ? 'selected' : 'outline'} aria-current={configuration ? 'page' : undefined}
            className="min-h-11" onClick={() => navigate('/migarden?tab=config')}>Cấu hình</Button>
        </nav>
      </div>
      {configuration && data && <ConfigStatus config={data.config} />}
      <Button type="button" variant="ghost" className="min-h-11" onClick={refresh} disabled={!online || state.isFetching}>
        <RefreshCw aria-hidden="true" /> Cập nhật
      </Button>
    </header>
    {state.isPending && <p role="status">Đang tải trạng thái Khu A…</p>}
    {state.isError && <p role="alert" className="rounded-lg bg-warn-bg p-3">
      Không đọc được trạng thái mới. {data ? 'Đang hiển thị báo cáo cuối đã nhận.' : 'Dùng Cập nhật để thử lại.'}
    </p>}
    {data && <>
      <div hidden={!configuration}>
        <Configuration config={data.config} connected={connected} onSaved={config => {
          cache.setQueryData<GardenState>(['migarden', 'state'], old => old ? { ...old, config } : old, { updatedAt: state.dataUpdatedAt })
          void cache.invalidateQueries({ queryKey: ['migarden'] })
        }} />
      </div>
      {history && <GardenHistory compact={false} onNavigate={() => navigate('/migarden', { replace: true })} />}
      {!configuration && !history && <>
        <OverviewStatus state={data} dataAt={state.dataUpdatedAt} now={now} online={online} connected={connected} refresh={refresh} />
        <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[minmax(0,2.1fr)_minmax(17rem,1fr)]">
          <WaterChart />
          <div className="grid min-w-0 gap-4">
            <NextSchedule next={data.next_schedule} fresh={!!fresh} />
            <GardenHistory compact onNavigate={() => navigate('/migarden?history=1')} />
          </div>
        </div>
      </>}
    </>}
  </section>
}
