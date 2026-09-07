import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell } from 'lucide-react'
import { apiRequest } from '@/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'
import { ReminderDevices } from '@/ReminderDevices'
import { activeReminder, reminderKey, reminderPreview, reminderTime, reminderStatus, vnInput,
  type Reminder, type ReminderSource, type ReminderSourceInfo } from '@/reminder-ui'

export function ReminderButton({ kind, sourceId }: { kind: ReminderSource; sourceId: string }) {
  const [open, setOpen] = useState(false)
  return <>
    <Button type="button" size="lg" variant="outline" data-testid="source-reminder" onClick={() => setOpen(true)}>
      <Bell aria-hidden="true" />Nhắc tôi
    </Button>
    {open && <ReminderEditor kind={kind} sourceId={sourceId} onClose={() => setOpen(false)} />}
  </>
}

export function ReminderEditor({ kind, sourceId, onClose }: {
  kind: ReminderSource; sourceId: string; onClose: () => void
}) {
  const source = useQuery({ queryKey: [...reminderKey, 'source', kind, sourceId],
    queryFn: ({ signal }) => apiRequest<ReminderSourceInfo>(`/api/reminders/source/${kind}/${sourceId}`, { signal }),
    ...NO_POLLING_QUERY_OPTIONS })
  const reminders = useQuery({ queryKey: [...reminderKey, 'active', kind, sourceId],
    queryFn: ({ signal }) => apiRequest<{ items: Reminder[] }>(
      `/api/reminders?section=active&kind=${kind}&source_id=${sourceId}`, { signal }),
    ...NO_POLLING_QUERY_OPTIONS })
  const current = reminders.data?.items.find(activeReminder)
  return <Dialog open onOpenChange={(value) => { if (!value) onClose() }}>
    <DialogContent className="max-h-[90dvh] overflow-y-auto" data-testid="reminder-editor">
      <DialogHeader><DialogTitle>Nhắc tôi</DialogTitle>
        <DialogDescription>Lời nhắc một lần · giờ Việt Nam</DialogDescription></DialogHeader>
      {source.isPending || reminders.isPending ? <p role="status">Đang tải…</p>
        : source.isError || reminders.isError ? <div role="alert"><p>Chưa tải được lời nhắc hoặc đối tượng không còn hiển thị.</p>
          <Button size="lg" variant="outline" onClick={() => { void source.refetch(); void reminders.refetch() }}>Thử lại</Button></div>
        : source.data && <ReminderFields key={`${current?.id ?? 'new'}-${current?.revision ?? 0}`}
          source={source.data} kind={kind} sourceId={sourceId} current={current} onClose={onClose} />}
    </DialogContent>
  </Dialog>
}

function ReminderFields({ source, kind, sourceId, current, onClose }: {
  source: ReminderSourceInfo; kind: ReminderSource; sourceId: string; current?: Reminder; onClose: () => void
}) {
  const client = useQueryClient()
  const [openedAt] = useState(Date.now)
  const [enabled, setEnabled] = useState(Boolean(current))
  const [mode, setMode] = useState(current?.mode ?? 'absolute')
  const [absolute, setAbsolute] = useState(current ? vnInput(current.due_at) : '')
  const [amount, setAmount] = useState(String(Math.abs(current?.offset_minutes ?? 15)))
  const [unit, setUnit] = useState('1')
  const [direction, setDirection] = useState((current?.offset_minutes ?? -15) <= 0 ? '-1' : '1')
  const [clock, setClock] = useState(current?.anchor_time?.slice(0, 5) ?? '')
  const preview = reminderPreview(source, mode, absolute, amount, unit, direction, clock)
  const relativeAvailable = kind !== 'tracker' && Boolean(source.anchor_at || source.anchor_day)
  const refresh = () => { void client.invalidateQueries({ queryKey: reminderKey }); onClose() }
  const save = useMutation({ mutationFn: () => apiRequest(`/api/reminders/${kind}/${sourceId}`, {
    method: 'PUT', body: JSON.stringify({ mode,
      ...(mode === 'absolute' ? { due_at: preview } : {
        offset_minutes: Number(amount) * Number(unit) * Number(direction),
        anchor_time: source.date_only ? clock : null }),
      expected_id: current?.id ?? null, expected_revision: current?.revision ?? null,
      expected_source_updated_at: source.updated_at ?? null,
    }),
  }), onSuccess: refresh,
  onError: () => { void client.invalidateQueries({ queryKey: [...reminderKey, 'active', kind, sourceId] });
    void client.invalidateQueries({ queryKey: [...reminderKey, 'source', kind, sourceId] }) } })
  const cancel = useMutation({ mutationFn: () => apiRequest(
    `/api/reminders/${current!.id}?revision=${current!.revision}`, { method: 'DELETE' }), onSuccess: refresh })
  const busy = save.isPending || cancel.isPending
  return <div className="space-y-4">
    <p className="break-words font-semibold">{source.title}</p>
    {current && <p role="status" className="text-sm text-muted-foreground">{reminderStatus[current.status]}</p>}
    {!source.open ? <p role="alert">Đối tượng đã hoàn thành hoặc bị xoá.</p> : <>
      <Button size="lg" variant={enabled ? 'selected' : 'outline'} aria-pressed={enabled}
        disabled={busy || current?.status === 'sending'} onClick={() => setEnabled(!enabled)}>
        {enabled ? 'Đã bật nhắc nhở' : 'Bật nhắc nhở'}</Button>
      {enabled && <div className="space-y-3">
        <ReminderDevices />
        <label className="block space-y-1 text-sm font-semibold">Cách đặt
          <Select value={mode} onValueChange={(v) => setMode(v as typeof mode)} disabled={busy}>
            <SelectTrigger className="min-h-11 w-full" aria-label="Cách đặt"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="absolute">Ngày giờ tùy chỉnh</SelectItem>
              {relativeAvailable && <SelectItem value="relative">Trước / sau mốc đã lưu</SelectItem>}</SelectContent>
          </Select></label>
        {mode === 'absolute' ? <label className="block space-y-1 text-sm font-semibold">Ngày giờ nhắc
          <Input data-testid="reminder-absolute" type="datetime-local" className="min-h-11 text-base"
            value={absolute} onChange={(e) => setAbsolute(e.target.value)} /></label>
          : <>
            <div className="flex flex-wrap gap-2">{[['15', '15 phút trước'], ['60', '1 giờ trước'], ['1440', '1 ngày trước']].map(([v, label]) =>
              <Button key={v} size="lg" variant="outline" onClick={() => { setAmount(v); setUnit('1'); setDirection('-1') }}>{label}</Button>)}</div>
            <div className="grid grid-cols-2 gap-2">
              <Select value={direction} onValueChange={setDirection}><SelectTrigger className="min-h-11 w-full" aria-label="Trước hay sau"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="-1">Trước</SelectItem><SelectItem value="1">Sau</SelectItem></SelectContent></Select>
              <Input aria-label="Khoảng thời gian" type="number" min="0" max="525600" step="1" className="min-h-11 text-base"
                value={amount} onChange={(e) => setAmount(e.target.value)} />
              <Select value={unit} onValueChange={setUnit}><SelectTrigger className="min-h-11 w-full" aria-label="Đơn vị thời gian"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="1">Phút</SelectItem><SelectItem value="60">Giờ</SelectItem><SelectItem value="1440">Ngày</SelectItem></SelectContent></Select>
            </div>
            {source.date_only && <label className="block space-y-1 text-sm font-semibold">Giờ mốc trong ngày
              <Input type="time" aria-label="Giờ mốc trong ngày" className="min-h-11 text-base" value={clock} onChange={(e) => setClock(e.target.value)} /></label>}
          </>}
        <p role="status" data-testid="reminder-preview" className="text-sm">{preview ? `Sẽ nhắc: ${reminderTime(preview)}` : 'Chọn đủ thời gian để xem giờ nhắc.'}</p>
        {preview && Date.parse(preview) <= openedAt && <p role="alert" className="text-sm text-bad">Giờ nhắc đã qua. Chọn một thời điểm trong tương lai.</p>}
        {source.is_private && <p className="text-sm text-muted-foreground">Thông báo trên màn hình khóa không hiện nội dung private.</p>}
      </div>}
    </>}
    {(save.error || cancel.error) && <p role="alert" className="text-sm text-bad">{(save.error || cancel.error)?.message}</p>}
    <div className="flex flex-wrap gap-2">
      {enabled ? <Button size="lg" data-testid="reminder-save" disabled={busy || !source.open || !preview || Date.parse(preview) <= openedAt || current?.status === 'sending'}
        onClick={() => save.mutate()}>{save.isPending ? 'Đang lưu…' : current ? 'Lưu lời nhắc' : 'Đặt nhắc mới'}</Button>
        : current && <Button size="lg" variant="destructive" disabled={busy} onClick={() => cancel.mutate()}>Tắt lời nhắc</Button>}
      <Button size="lg" variant="outline" onClick={onClose}>Đóng</Button>
    </div>
  </div>
}
