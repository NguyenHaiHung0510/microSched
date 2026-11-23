import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { onlineManager, useMutation, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, Droplet, RefreshCw, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { navigate, queryParams } from '@/lib/route'
import { cn } from '@/lib/utils'
import { garden, gardenKey, useGardenState, type Command, type Forecast, type Preview } from './api'
import { PrimaryLiveStatus } from '@/LiveStatus'
import { Configuration, ConfigStatus } from './Configuration'
import { GardenHistory, GardenRecent } from './GardenHistory'
import { useGardenTimeline } from './historyQuery'
import { WaterChart } from './WaterChart'
import { ScheduleTrace } from './ScheduleTrace'
import { GardenVersions } from './GardenVersions'
import { GardenHealth } from './GardenHealth'
import type { ConfigView } from './api'
import { displayedSession, duration, errorText, explainReason, instantLabel, sources, statusLabels, stopwatch, timeLabel } from './presentation'
import { useHumanActive, useHumanInputAt } from '@/human-activity'
import { gardenServerNow, OUTPUT_FRESH_MS, patchGardenState, refreshGarden, type GardenReading } from './liveReading'
import './garden.css'

function NextSchedule({ next, fresh, config }: { next: Forecast; fresh: boolean; config: ConfigView }) {
  const projection = config.schedule_projection
  const possible = projection?.possible_previous_run
  next = projection ? (possible ? projection.last_confirmed : projection.saved) : next
  const empty = {
    no_applied_config: 'Chưa có lịch được ESP32 xác nhận.',
    paused: 'Lịch đã áp dụng đang tạm dừng.',
    no_future_occurrence: 'Không còn lượt sắp tới trong khoảng hiệu lực.',
    scheduled: '',
  }[next.status]
  return <Card data-testid="garden-next-schedule">
    <CardHeader><h3 className="text-xl font-extrabold">Lượt sắp tới</h3></CardHeader>
    <CardContent className="space-y-2">
      <ScheduleTrace config={config} />
      {next.next_at && next.duration_seconds !== null
        ? <div className="flex items-center gap-3 rounded-lg bg-accent p-3">
          <CalendarDays className="size-6 shrink-0 text-primary" aria-hidden="true" />
          <div><time className="text-xl font-extrabold tabular-nums" dateTime={next.next_at}>{instantLabel(next.next_at)}</time>
            <p className="text-sm">{possible ? 'Có thể vẫn tưới · ' : ''}{duration(next.duration_seconds)} · {possible ? 'Theo bản ESP xác nhận gần nhất' : 'Theo lịch'}</p></div>
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
  state: GardenReading; dataAt: number; now: number; online: boolean; connected: boolean; refresh: () => void;
}) {
  const client = useQueryClient()
  const stateKey = gardenKey('state')
  const human = useHumanActive()
  const opener = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  const [minutes, setMinutes] = useState('')
  const [preview, setPreview] = useState<{ record: Preview; localExpires: number } | null>(null)
  const [formError, setFormError] = useState('')
  const [startNotice, setStartNotice] = useState('')
  const [stopNotice, setStopNotice] = useState('')
  const device = state.snapshot
  const active = device?.active_session
  const display = displayedSession(state, dataAt, now, true)
  const max = state.config.applied?.policy.max_session_seconds ?? 0
  const canStart = online && connected && human && display.fresh && device?.output === 'off' && !active && state.start_block_reason === null && Boolean(max)
  const applyCommand = (key: 'start_request' | 'stop_request', data: Command) => patchGardenState(client, stateKey, { [key]: data })
  const getPreview = useMutation({
    mutationFn: garden.preview, retry: false, networkMode: 'always',
    onMutate: () => Date.now(),
    onSuccess: (record, _minutes, at) => {
      setPreview({ record, localExpires: Math.min((at ?? Date.now()) + 45_000, Date.now() + Math.max(0, Date.parse(record.expires_at) - gardenServerNow(state, dataAt, Date.now()))) })
    },
    onError: error => { setFormError(errorText(error, 'Không lấy được bản xem trước. Kiểm tra kết nối và thử lại.')); refresh() },
  })
  const confirm = useMutation({
    mutationFn: garden.confirm, retry: false, networkMode: 'always',
    onSuccess: async data => { await applyCommand('start_request', data); setOpen(false); setStartNotice('') },
    onError: error => {
      const detail = 'Chưa xác nhận kết quả gửi. Xem trạng thái trước khi gửi yêu cầu mới.'
      setFormError(errorText(error, detail))
      setStartNotice(errorText(error, detail))
      refresh()
    },
  })
  const stop = useMutation({
    mutationFn: garden.stop, retry: false, networkMode: 'always',
    onSuccess: async data => { setStopNotice(''); setStartNotice(''); await applyCommand('stop_request', data) },
    onError: error => {
      setStopNotice(errorText(error, 'Chưa xác nhận gửi được Dừng. Kiểm tra tại tủ nếu cần dừng ngay.'))
      refresh()
    },
  })
  const liveAt = display.live && active?.started_at ? timeLabel(active.started_at) : null
  const headline = display.fresh && device?.output === 'off' ? 'Đầu ra tắt'
    : display.fresh && device?.output === 'on' ? 'Đang tưới' : 'Chưa rõ trạng thái'
  const confirmed = state.confirmedOutput
  return <>
    <div className={cn('rounded-xl border px-4 py-3', display.live ? 'border-primary/25 bg-accent' : 'border-muted bg-background')}
      data-testid="garden-now">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1">
          <p data-testid="garden-output" className="flex items-center gap-2 text-base font-extrabold lg:text-lg">
            <Droplet aria-hidden="true" className="size-5 shrink-0 text-primary" />
            {headline}
          </p>
          {active && <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 sm:border-l sm:border-muted sm:pl-4">
            <span>{sources[active.trigger_source]}</span>
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
            disabled={!online || !state.stop_available || stop.isPending}
            onClick={() => { setOpen(false); setStopNotice(''); stop.mutate() }}>
            <Square aria-hidden="true" /> {stop.isPending ? 'Đang gửi Dừng…' : 'Dừng tưới'}
          </Button>
        </div>
      </div>
      <div className="mt-2 space-y-1 text-sm">
        {state.snapshot_received_at && <p className="text-muted-foreground">
          Báo cáo cuối lúc <time dateTime={state.snapshot_received_at}>{instantLabel(state.snapshot_received_at)}</time>
        </p>}
        {(!display.fresh || device?.output === 'unknown' || !device) && <p data-testid="garden-last-confirmed">
          {confirmed ? <>Lần cuối xác nhận: {confirmed.output === 'on' ? 'Đầu ra bật' : 'Đầu ra tắt'} · <time dateTime={confirmed.receivedAt}>{instantLabel(confirmed.receivedAt)}</time></> : 'Chưa có xác nhận đầu ra'}
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
            <Button type="button" disabled={confirm.isPending || !canStart || now >= preview.localExpires}
              onClick={() => { if (!canStart || Date.now() >= preview.localExpires || !displayedSession(state, dataAt, Date.now(), connected).fresh) return; setFormError(''); confirm.mutate(preview.record.preview_id) }}>
              {confirm.isPending ? 'Đang gửi…' : 'Xác nhận tưới'}
            </Button>
          </DialogFooter>
        </> : <form className="space-y-3" onSubmit={event => {
          event.preventDefault()
          if (!canStart || !displayedSession(state, dataAt, Date.now(), connected).fresh) return
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

const gardenTabs = [
  { id: 'overview', label: 'Tổng quan', target: '/migarden' },
  { id: 'history', label: 'Lịch sử', target: '/migarden?tab=history' },
  { id: 'config', label: 'Cấu hình', target: '/migarden?tab=config' },
] as const

export function MiGardenScreen({ location, leave, configVersion }: {
  location: string; leave: (action: () => void) => void; configVersion: number;
}) {
  const route = queryParams(location)
  const configuration = route.get('tab') === 'config'
  const history = !configuration && (route.get('tab') === 'history' || !route.has('tab') && route.get('history') === '1')
  const current = configuration ? 'config' : history ? 'history' : 'overview'
  const go = (target: string) => leave(() => navigate(target))
  const [tick, setNow] = useState(() => Date.now())
  const active = useHumanActive()
  const inputAt = useHumanInputAt()
  const now = active ? Math.max(tick, inputAt) : tick
  const stateKey = gardenKey('state')
  const online = useSyncExternalStore(onlineManager.subscribe, () => onlineManager.isOnline())
  const state = useGardenState(!history)
  const timeline = useGardenTimeline(history)
  const cache = useQueryClient()
  const data = state.data
  useEffect(() => {
    if (configuration || history || !active) return
    const id = window.setInterval(() => { if (!document.hidden) setNow(Date.now()) }, 1000)
    return () => window.clearInterval(id)
  }, [configuration, history, active])
  useEffect(() => {
    if (configuration || history || !active || !data?.snapshot_received_at) return
    const remaining = OUTPUT_FRESH_MS - (gardenServerNow(data, state.dataUpdatedAt, Date.now()) - Date.parse(data.snapshot_received_at))
    if (remaining <= 0) return
    const timer = window.setTimeout(() => setNow(Date.now()), remaining)
    return () => window.clearTimeout(timer)
  }, [configuration, history, active, data, state.dataUpdatedAt])
  const connected = online && !state.isError
  const fresh = data && displayedSession(data, state.dataUpdatedAt, now, connected).fresh
  const refresh = () => refreshGarden(cache)
  return <section aria-labelledby="migarden-title" data-testid="migarden-screen" className="space-y-4">
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex min-w-0 flex-wrap items-start gap-x-6 gap-y-3">
        <div><h2 id="migarden-title" className="text-3xl font-extrabold tracking-tight">miGarden</h2>
          <p className="text-base text-muted-foreground">Khu A</p></div>
        <nav className="flex flex-wrap gap-2" aria-label="Mục trong miGarden">
          {gardenTabs.map(tab => <Button key={tab.id} type="button"
            variant={current === tab.id ? 'selected' : 'outline'} aria-current={current === tab.id ? 'page' : undefined}
            className="min-h-11" onClick={() => { if (current !== tab.id) go(tab.target) }}>{tab.label}</Button>)}
        </nav>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <PrimaryLiveStatus query={history ? timeline.query : state} />
        {configuration && data && <ConfigStatus config={data.config} />}
        <Button type="button" variant="ghost" className="min-h-11" onClick={refresh}
          disabled={!online || (history ? timeline.badRange || timeline.query.isFetching : state.isFetching)}>
          <RefreshCw aria-hidden="true" /> Cập nhật
        </Button>
      </div>
    </header>
    {!history && state.isPending && <p role="status">Đang tải trạng thái Khu A…</p>}
    {!history && state.isError && <p role="alert" className="rounded-lg bg-warn-bg p-3">
      Không đọc được trạng thái mới. {data ? 'Đang hiển thị báo cáo cuối đã nhận.' : 'Dùng Cập nhật để thử lại.'}
    </p>}
    {!history && !data && <p>Chưa có xác nhận đầu ra</p>}
    {data && <>
      <div hidden={!configuration}>
        {configuration && data.config.desired && <div className="mb-3 space-y-2"><ScheduleTrace config={data.config} /><Button variant="outline" onClick={() => go('/migarden?tab=history&version=' + encodeURIComponent(data.config.desired!.config_ref))}>Xem bản đã lưu</Button>{data.config.applied && <Button variant="ghost" onClick={() => go('/migarden?tab=history&version=' + encodeURIComponent(data.config.applied!.config_ref))}>Xem bản ESP xác nhận gần nhất</Button>}</div>}
        <Configuration key={configVersion} config={data.config} connected={connected} onSaved={config => patchGardenState(cache, stateKey, { config })} />
      </div>
      {!configuration && !history && <>
        <OverviewStatus state={data} dataAt={state.dataUpdatedAt} now={now} online={online} connected={connected} refresh={refresh} />
        <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[minmax(0,2.1fr)_minmax(17rem,1fr)]">
          <WaterChart />
          <div className="grid min-w-0 gap-4">
            <NextSchedule next={data.next_schedule} fresh={!!fresh} config={data.config} />
            <GardenHealth state={data} dataAt={state.dataUpdatedAt} now={now} />
            <GardenRecent currentRequests={[data.start_request, data.stop_request]} onNavigate={() => go('/migarden?tab=history')} />
          </div>
        </div>
      </>}
    </>}
    {history && <div className="grid min-w-0 items-start gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]"><GardenHistory timeline={timeline} onVersion={ref => go('/migarden?tab=history&version=' + encodeURIComponent(ref))} /><GardenVersions selected={route.get('version')} onSelect={ref => go('/migarden?tab=history&version=' + encodeURIComponent(ref))} /></div>}
  </section>
}
