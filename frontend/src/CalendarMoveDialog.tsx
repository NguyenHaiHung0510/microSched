import { useEffect, useId, useRef, useState } from 'react'
import { formatFullVietnameseDate } from '@/calendar-scroll'
import { formatVietnamTime } from '@/calendar-ui'
import { shiftedAnnotation, shiftedTaskSchedule, validMoveDay, type CalendarMoveTarget } from '@/calendar-move'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'

export function CalendarMoveDialog({ target, pending, error, onMove, onClose, onEdit }: {
  target: CalendarMoveTarget
  pending: boolean
  error: string | null
  onMove: (day: string) => void
  onClose: () => void
  onEdit: () => void
}) {
  const [day, setDay] = useState(target.grabbedDay)
  const [localError, setLocalError] = useState<string | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const errorId = useId()
  useEffect(() => { if (error) input.current?.focus() }, [error])
  const valid = validMoveDay(day)
  const dates = valid && target.kind === 'annotation' ? shiftedAnnotation(target.item, target.grabbedDay, day) : null
  const schedule = valid && target.kind === 'task' ? shiftedTaskSchedule(target.item, day) : null
  const message = localError ?? error
  return <Dialog open onOpenChange={open => !open && onClose()}>
    <DialogContent data-testid="calendar-move-dialog" className="max-h-[85vh] overflow-y-auto sm:max-w-md"
      onCloseAutoFocus={event => {
        event.preventDefault()
        document.querySelector<HTMLButtonElement>(`[data-testid="calendar-day-cell"][data-day="${target.grabbedDay}"]`)?.focus({ preventScroll: true })
      }}>
      <DialogHeader>
        <DialogTitle>Chuyển ngày</DialogTitle>
        <DialogDescription>{target.kind === 'task' ? 'Giữ nguyên nội dung và giờ của việc.' : 'Giữ nguyên độ dài dấu ngày; ngày đang chọn được chuyển tới ngày mới.'}</DialogDescription>
      </DialogHeader>
      <p className="min-w-0 break-words text-sm font-bold [overflow-wrap:anywhere]">{target.kind === 'task' ? target.item.title : target.item.label}</p>
      <form className="space-y-4" onSubmit={event => {
        event.preventDefault()
        if (!valid) { setLocalError('Chọn ngày hợp lệ.'); input.current?.focus(); return }
        if (!pending) onMove(day)
      }}>
        <label className="block space-y-1.5 text-sm font-semibold">
          <span>{target.kind === 'annotation' ? 'Chuyển ngày đã chọn tới' : 'Ngày mới'}</span>
          <Input ref={input} name="calendar-move-day" autoComplete="off" type="date" required value={day} disabled={pending} className="h-11 bg-card"
            aria-invalid={Boolean(message) || undefined} aria-describedby={message ? errorId : undefined}
            onChange={event => { setDay(event.target.value); setLocalError(null); onEdit() }} />
        </label>
        {dates ? <p data-testid="calendar-move-preview" className="break-words rounded-lg bg-accent p-3 text-sm">
          Sau khi chuyển: {formatFullVietnameseDate(dates.starts_on)} – {formatFullVietnameseDate(dates.ends_on)}
          {' · '}{(Date.parse(dates.ends_on) - Date.parse(dates.starts_on)) / 86400000 + 1} ngày
        </p> : schedule ? <p data-testid="calendar-move-preview" className="break-words text-sm">
          {formatFullVietnameseDate(day)}{schedule.due_at ? ` · ${formatVietnamTime({ starts_at: schedule.due_at, ends_at: schedule.due_at, all_day: false }).split('–')[0]}` : ''}
        </p> : null}
        {message ? <p id={errorId} data-testid="calendar-move-error" role="alert" className="break-words text-sm text-bad">{message}</p> : null}
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" className="min-h-11" onClick={onClose}>Huỷ</Button>
          <Button type="submit" className="min-h-11" disabled={pending}>{pending ? 'Đang chuyển ngày…' : 'Chuyển ngày'}</Button>
        </div>
      </form>
    </DialogContent>
  </Dialog>
}
