import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Bell } from 'lucide-react'
import { apiRequest } from '@/api'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'
import { ReminderEditor } from '@/ReminderEditor'
import { ReminderSourceDialog } from '@/ReminderSourceDialog'
import { reminderKey, reminderStatus, reminderTime, type Reminder, type ReminderSource } from '@/reminder-ui'
import type { Tracker } from '@/tracker-ui'
import { PrivateMarker } from '@/PrivateMarker'
import { ReminderDevices } from '@/ReminderDevices'

export function ReminderCenter() {
  const [open, setOpen] = useState(() => new URLSearchParams(window.location.search).has('reminders'))
  const [section, setSection] = useState('upcoming')
  const [offset, setOffset] = useState(0)
  const [edit, setEdit] = useState<{ kind: ReminderSource; id: string } | null>(null)
  const [source, setSource] = useState<{ kind: ReminderSource; id: string } | null>(null)
  const rows = useQuery({ queryKey: [...reminderKey, 'center', section, offset],
    queryFn: ({ signal }) => apiRequest<{ items: Reminder[]; has_more: boolean }>(
      `/api/reminders?section=${section}&offset=${offset}`, { signal }),
    enabled: open, ...NO_POLLING_QUERY_OPTIONS })
  const trackers = useQuery({ queryKey: [...reminderKey, 'recurring'],
    queryFn: ({ signal }) => apiRequest<{ items: Tracker[] }>('/api/tracker/trackers', { signal }),
    enabled: open && section === 'upcoming', ...NO_POLLING_QUERY_OPTIONS })
  return <>
    <Button type="button" size="lg" variant="outline" aria-label="Nhắc nhở" data-testid="reminder-center-open" onClick={() => setOpen(true)}>
      <Bell aria-hidden="true" /><span className="hidden sm:inline">Nhắc nhở</span>
    </Button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent data-testid="reminder-center" className="inset-y-0 right-0 left-auto h-dvh max-h-dvh w-full max-w-full translate-x-0 translate-y-0 content-start overflow-y-auto rounded-none p-5 sm:max-w-lg">
        <DialogHeader><DialogTitle>Nhắc nhở</DialogTitle><DialogDescription>Lịch nhắc của bạn · giờ Việt Nam</DialogDescription></DialogHeader>
        <ReminderDevices />
        <div className="flex flex-wrap gap-2" aria-label="Nhóm lời nhắc">
          {[['upcoming', 'Sắp tới'], ['attention', 'Cần chú ý']].map(([value, label]) =>
            <Button key={value} size="lg" variant={section === value ? 'selected' : 'outline'} aria-pressed={section === value}
              onClick={() => { setSection(value); setOffset(0) }}>{label}</Button>)}
          <Button size="lg" variant={section === 'history' ? 'selected' : 'ghost'} aria-expanded={section === 'history'}
            onClick={() => { setSection(section === 'history' ? 'upcoming' : 'history'); setOffset(0) }}>Lịch sử</Button>
          <Button size="lg" variant="ghost" onClick={() => { void rows.refetch(); void trackers.refetch() }}>Làm mới</Button>
        </div>
        {rows.isPending ? <p role="status">Đang tải…</p> : rows.isError ? <p role="alert">Chưa tải được lời nhắc. Bấm Làm mới để thử lại.</p>
          : <div className="space-y-3">{rows.data.items.length === 0 && <p className="text-sm text-muted-foreground">Không có lời nhắc trong nhóm này.</p>}
            {rows.data.items.map((row) => <article key={row.id} data-testid="reminder-row" className="space-y-2 rounded-lg border p-3">
              <p className="break-words font-semibold">{row.source_title}</p>
              {row.is_private && <PrivateMarker />}
              <p className="text-sm">{reminderTime(row.due_at)} · Một lần</p>
              <p className="text-sm text-muted-foreground">{reminderStatus[row.status]}</p>
              <div className="flex flex-wrap gap-2">
                <Button size="lg" variant="outline" onClick={() => setSource({ kind: row.source_kind, id: row.source_id })}>Mở đối tượng</Button>
                {row.source_open && <Button size="lg" variant="outline" onClick={() => setEdit({ kind: row.source_kind, id: row.source_id })}>
                  {['pending', 'sending', 'needs_reschedule'].includes(row.status) ? 'Sửa / tắt nhắc' : 'Đặt nhắc mới'}</Button>}
              </div>
            </article>)}
            <div className="flex gap-2">{offset > 0 && <Button size="lg" variant="outline" onClick={() => setOffset(Math.max(0, offset - 50))}>Trang trước</Button>}
              {rows.data.has_more && <Button size="lg" variant="outline" onClick={() => setOffset(offset + 50)}>Trang sau</Button>}</div>
          </div>}
        {section === 'upcoming' && <section className="space-y-3 border-t pt-4"><h3 className="font-semibold">Nhắc định kỳ</h3>
          {trackers.isError ? <p role="alert">Chưa tải được lịch định kỳ.</p> : trackers.data?.items.filter((t) => t.reminder_time).map((tracker) =>
            <article key={tracker.id} className="space-y-2 rounded-lg border p-3"><p className="break-words font-semibold">{tracker.name}</p>
              {tracker.is_private && <PrivateMarker />}
              <p className="text-sm">{tracker.next_reminder_at ? reminderTime(tracker.next_reminder_at) : 'Chưa xác định lần tiếp theo'}</p>
              <Button size="lg" variant="outline" onClick={() => setSource({ kind: 'tracker', id: tracker.id })}>Mở / sửa tracker</Button>
            </article>)}</section>}
      </DialogContent>
    </Dialog>
    {edit && <ReminderEditor kind={edit.kind} sourceId={edit.id} onClose={() => setEdit(null)} />}
    {source && <ReminderSourceDialog kind={source.kind} sourceId={source.id} onClose={() => setSource(null)} />}
  </>
}
