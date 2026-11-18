import { useRef, useState } from 'react'
import { useIsMutating, useMutation, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, RotateCcw, Save, SlidersHorizontal } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { garden, gardenConfigMutation, type Bundle, type Config, type ConfigView, type Recurrence } from './api'
import { duration, errorText, explainReason, fromLocal, instantLabel, localInput } from './presentation'

const patterns = {
  once: 'Một lần', daily: 'Hằng ngày', weekly: 'Theo thứ', interval: 'Theo chu kỳ',
}
const weekdays = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN']
type Form = {
  enabled: boolean; effective: string; until: string; watering: string; kind: Recurrence['kind'];
  at: string; localTime: string; weekdays: number[]; anchor: string; interval: string;
  manual: string; perRun: string; total: string;
}
type Draft = { baseline: Form; ref: string | null; value: Form }

function formFrom(config: Config | null, initialTime: string): Form {
  const schedule = config?.schedule
  const recurrence = schedule?.recurrence
  const effective = schedule ? localInput(schedule.effective_from) : initialTime
  return {
    enabled: schedule?.enabled ?? false,
    effective, until: schedule?.effective_until ? localInput(schedule.effective_until) : '',
    watering: String((schedule?.duration_seconds ?? 900) / 60),
    kind: recurrence?.kind ?? 'daily',
    at: recurrence?.kind === 'once' ? localInput(recurrence.at) : effective,
    localTime: recurrence?.kind === 'daily' || recurrence?.kind === 'weekly' ? recurrence.at_local_time : '07:00',
    weekdays: recurrence?.kind === 'weekly' ? recurrence.days_of_week : [],
    anchor: recurrence?.kind === 'interval' ? localInput(recurrence.anchor_at) : effective,
    interval: recurrence?.kind === 'interval' ? String(recurrence.interval_minutes) : '1440',
    manual: String((config?.policy.manual_duration_seconds ?? 900) / 60),
    perRun: String((config?.policy.max_session_seconds ?? 1800) / 60),
    total: String((config?.policy.max_window_seconds ?? 7200) / 60),
  }
}

function seconds(value: string): number {
  const result = Number(value) * 60
  if (!value || !Number.isFinite(result) || result < 15 || result > 10_800 || result % 15 !== 0) {
    throw new Error('Thời lượng phải từ 0,25 đến 180 phút, theo bước 15 giây.')
  }
  return result
}

function bundleFrom(value: Form): Bundle {
  const manual = seconds(value.manual)
  const maxSession = seconds(value.perRun)
  const maxWindow = seconds(value.total)
  const watering = seconds(value.watering)
  if (!(manual <= maxSession && maxSession <= maxWindow)) {
    throw new Error('Thời lượng nút START ≤ tối đa mỗi lượt ≤ tổng tối đa trong 3 giờ.')
  }
  if (watering > maxSession) throw new Error('Thời lượng lịch không được vượt mức tối đa mỗi lượt.')
  const start = fromLocal(value.effective)
  const until = value.until ? fromLocal(value.until) : null
  if (until && until <= start) throw new Error('Mốc kết thúc phải sau mốc bắt đầu.')
  let recurrence: Recurrence
  if (value.kind === 'once') {
    const at = fromLocal(value.at)
    if (value.enabled && (at < start || (until !== null && at >= until))) {
      throw new Error('Lượt tưới một lần phải nằm trong khoảng hiệu lực.')
    }
    recurrence = { kind: 'once', at }
  } else if (value.kind === 'interval') {
    const n = Number(value.interval)
    if (!Number.isInteger(n) || n < 1 || n > 2_147_483_647) throw new Error('Chu kỳ phải là số phút nguyên, lớn hơn 0.')
    recurrence = { kind: 'interval', anchor_at: fromLocal(value.anchor), interval_minutes: n }
  } else {
    if (!/^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/.test(value.localTime)) throw new Error('Chọn giờ tưới.')
    if (value.kind === 'weekly' && !value.weekdays.length) throw new Error('Chọn ít nhất một thứ trong tuần.')
    recurrence = value.kind === 'daily'
      ? { kind: 'daily', at_local_time: value.localTime }
      : { kind: 'weekly', at_local_time: value.localTime, days_of_week: value.weekdays }
  }
  return {
    policy: { manual_duration_seconds: manual, max_session_seconds: maxSession, max_window_seconds: maxWindow, window_seconds: 10800 },
    schedule: { enabled: value.enabled, effective_from: start, effective_until: until, duration_seconds: watering, recurrence },
  }
}

function DurationField({ id, label, value, change, disabled }: { id: string; label: string; value: string; change: (v: string) => void; disabled: boolean }) {
  return <label htmlFor={id} className="grid grid-cols-[minmax(0,1fr)_minmax(5rem,7rem)_auto] items-center gap-2 text-sm">
    <span>{label}</span><Input id={id} type="number" value={value} min={0.25} max={180} step={0.25} required disabled={disabled}
      className="min-h-11 text-base" onChange={event => change(event.target.value)} /><span>phút</span>
  </label>
}

function DateField({ id, label, value, change, disabled, required = true }: {
  id: string; label: string; value: string; change: (v: string) => void; disabled: boolean; required?: boolean;
}) {
  return <label htmlFor={id} className="grid min-w-0 gap-1 text-sm">
    {label}<Input id={id} type="datetime-local" className="min-h-11 w-full min-w-0 text-base"
      required={required} value={value} disabled={disabled} onChange={event => change(event.target.value)} />
  </label>
}

export function ConfigStatus({ config }: { config: ConfigView }) {
  const heading = {
    not_saved: 'Chưa lưu cấu hình', pending: 'Đã lưu · Chờ ESP32 áp dụng',
    rejected: 'ESP32 báo chưa áp dụng được', applied: 'ESP32 đã xác nhận áp dụng',
  }[config.application_status]
  return <div role="status" className="max-w-full space-y-0.5 text-sm">
    <p className="font-bold">{heading}</p>
    {config.desired_saved_at && <p className="text-muted-foreground">Lưu {instantLabel(config.desired_saved_at)}</p>}
    {config.applied_confirmed_at && <p className="text-muted-foreground">
      Xác nhận {instantLabel(config.applied_confirmed_at)}
      {config.applied?.config_ref !== config.desired?.config_ref && ' · Bản áp dụng trước đó'}
    </p>}
    {config.reason && <p className="break-words">{explainReason(config.reason)}</p>}
  </div>
}

export function Configuration({ config, connected, onSaved }: {
  config: ConfigView; connected: boolean; onSaved: (value: ConfigView) => void;
}) {
  const [initial] = useState(() => localInput(new Date().toISOString()))
  const [draft, setDraft] = useState<Draft | null>(null)
  const [validation, setValidation] = useState('')
  const saving = useRef(false)
  const queryClient = useQueryClient()
  const pending = useIsMutating({ mutationKey: gardenConfigMutation }) > 0
  const saveInFlight = () => saving.current || queryClient.isMutating({ mutationKey: gardenConfigMutation }) > 0
  const baseline = formFrom(config.desired, initial)
  const ref = config.desired?.config_ref ?? null
  const value = draft?.value ?? baseline
  const dirty = Boolean(draft && JSON.stringify(draft.value) !== JSON.stringify(draft.baseline))
  const conflict = Boolean(draft && draft.ref !== ref)
  const write = useMutation({
    mutationKey: gardenConfigMutation,
    mutationFn: ({ bundle, expected }: { bundle: Bundle; expected: string | null }) => garden.save(bundle, expected),
    retry: false, networkMode: 'always',
    onSuccess: result => { setDraft(null); setValidation(''); onSaved(result) },
    onSettled: () => { saving.current = false },
  })
  function edit<K extends keyof Form>(key: K, newValue: Form[K]) {
    if (saveInFlight()) return
    setDraft(prior => ({ baseline: prior?.baseline ?? baseline, ref: prior ? prior.ref : ref,
      value: { ...(prior?.value ?? baseline), [key]: newValue } }))
    setValidation('')
    write.reset()
  }
  return <form className="space-y-4" data-update-dirty={dirty ? 'true' : undefined} onSubmit={event => {
    event.preventDefault()
    if (saveInFlight() || conflict) return
    try {
      const bundle = bundleFrom(value)
      saving.current = true
      write.mutate({ bundle, expected: draft ? draft.ref : ref })
    }
    catch (error) { setValidation(error instanceof Error ? error.message : 'Kiểm tra lại các trường.') }
  }}>
    <div className="grid items-start gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader className="border-b border-muted bg-background pb-3">
          <h3 className="flex items-center gap-2 text-lg font-extrabold"><CalendarDays aria-hidden="true" className="size-5 text-primary" /> Lịch tưới</h3>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex min-h-11 items-center gap-4">
            <Checkbox id="garden-enabled" className="size-6" checked={value.enabled} disabled={pending} onCheckedChange={v => edit('enabled', v === true)} />
            <label htmlFor="garden-enabled" className="cursor-pointer py-2 font-bold">Bật lịch</label>
          </div>
          <p className="text-sm text-muted-foreground">Giờ Hà Nội (UTC+7). Các thay đổi lịch có hiệu lực sau khi ESP32 áp dụng.</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <DateField id="garden-effective" label="Có hiệu lực từ" value={value.effective} change={v => edit('effective', v)} disabled={pending} />
            <DateField id="garden-until" label="Kết thúc hiệu lực (tùy chọn)" value={value.until} change={v => edit('until', v)} disabled={pending} required={false} />
          </div>
          <div className="grid gap-1">
            <label htmlFor="garden-kind">Lặp lại</label>
            <Select value={value.kind} disabled={pending} onValueChange={v => edit('kind', v as Form['kind'])}>
              <SelectTrigger id="garden-kind" size="lg" className="w-full text-base" disabled={pending}><SelectValue /></SelectTrigger>
              <SelectContent>{Object.entries(patterns).map(([type, label]) => <SelectItem value={type} key={type}>{label}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          {value.kind === 'once' && <DateField id="garden-once" label="Ngày và giờ tưới" value={value.at} change={v => edit('at', v)} disabled={pending} />}
          {value.kind === 'interval' && <>
            <DateField id="garden-anchor" label="Mốc đầu chu kỳ" value={value.anchor} change={v => edit('anchor', v)} disabled={pending} />
            <label htmlFor="garden-interval" className="grid gap-1">Lặp mỗi (phút)
              <Input id="garden-interval" className="min-h-11 text-base" type="number" min={1} max={2147483647}
                required value={value.interval} disabled={pending} onChange={event => edit('interval', event.target.value)} />
            </label>
          </>}
          {(value.kind === 'daily' || value.kind === 'weekly') && <label htmlFor="garden-time" className="grid min-w-0 gap-1">
            Giờ tưới<Input id="garden-time" className="min-h-11 w-full text-base" type="time" required
              value={value.localTime} disabled={pending} onChange={event => edit('localTime', event.target.value)} />
          </label>}
          {value.kind === 'weekly' && <fieldset className="space-y-1">
            <legend>Thứ trong tuần</legend>
            <div className="flex flex-wrap gap-2">
              {weekdays.map((label, i) => <Button key={label} type="button" className="min-h-11 min-w-11" aria-pressed={value.weekdays.includes(i + 1)} disabled={pending}
                variant={value.weekdays.includes(i + 1) ? 'selected' : 'outline'} onClick={() => edit('weekdays',
                  value.weekdays.includes(i + 1) ? value.weekdays.filter(day => day !== i + 1) : [...value.weekdays, i + 1].sort())}>
                {label}
              </Button>)}
            </div>
          </fieldset>}
          <DurationField id="garden-watering" label="Thời lượng mỗi lần" value={value.watering} change={v => edit('watering', v)} disabled={pending} />
          <p className="rounded-lg bg-accent p-3 font-bold text-accent-foreground">
            {value.enabled ? patterns[value.kind] + (value.kind === 'daily' || value.kind === 'weekly' ? ' lúc ' + value.localTime : '') +
              (Number(value.watering) > 0 ? ' · ' + duration(Math.round(Number(value.watering) * 60)) : '') : 'Lịch đang tạm dừng trong bản này'}
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="border-b border-muted bg-background pb-3">
          <h3 className="flex items-center gap-2 text-lg font-extrabold"><SlidersHorizontal aria-hidden="true" className="size-5 text-primary" /> Nút tại tủ và giới hạn tưới</h3>
        </CardHeader>
        <CardContent className="space-y-3">
          <DurationField id="garden-manual" label="Thời lượng nút START" value={value.manual} change={v => edit('manual', v)} disabled={pending} />
          <DurationField id="garden-run-max" label="Tối đa mỗi lượt" value={value.perRun} change={v => edit('perRun', v)} disabled={pending} />
          <DurationField id="garden-window-max" label="Tổng tối đa" value={value.total} change={v => edit('total', v)} disabled={pending} />
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-muted px-3 py-2">
            <span>Trong bất kỳ</span><strong>3 giờ nào</strong>
          </div>
          <p className="text-sm text-muted-foreground">Giới hạn áp dụng chung cho lịch, web và nút tại tủ. Số phút có thể nhập theo bước 0,25 phút (15 giây).</p>
          <p className="text-sm text-muted-foreground">Bản mới áp dụng khi Controller rảnh. Lượt đang chạy giữ thời lượng đã nhận.</p>
        </CardContent>
      </Card>
    </div>
    {(validation || conflict || write.isError) && <p role="alert" className="rounded-lg bg-bad-bg p-3 text-sm text-bad">
      {validation || (conflict ? explainReason('config_conflict') : errorText(write.error, 'Chưa xác nhận lưu. Kiểm tra cấu hình hiện tại; bản nhập vẫn còn.'))}
    </p>}
    <div className="flex flex-wrap items-center justify-end gap-2 border-t border-muted pt-3">
      {!connected && <p className="mr-auto text-sm text-muted-foreground">Mất kết nối với web. Chưa lưu thay đổi.</p>}
      <Button type="button" variant="outline" className="min-h-11" disabled={pending || !draft} onClick={() => {
        if (saveInFlight()) return
        setDraft(null); setValidation(''); write.reset()
      }}><RotateCcw aria-hidden="true" /> {conflict ? 'Dùng bản đã lưu' : 'Đặt lại thay đổi'}</Button>
      <Button type="submit" className="min-h-11" disabled={!connected || pending || conflict || (!dirty && Boolean(config.desired))}>
        <Save aria-hidden="true" /> {pending ? 'Đang lưu…' : 'Lưu cấu hình'}
      </Button>
    </div>
  </form>
}
