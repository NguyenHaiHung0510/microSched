import { type FormEvent, useState } from 'react'

import {
  allDayVietnamRange,
  todayInVietnam,
  toVietnamDateTimeInput,
  vietnamInputToIso,
  type CalendarEvent,
  type CalendarSource,
} from '@/calendar-ui'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'

export function EventForm({
  initial,
  manualSources,
  pending,
  onSubmit,
  onCancel,
  open,
  onOpenChange,
  initialEvent,
  defaultDate,
  allowedSourceIds,
  onSuccess,
  icsWarning,
  error,
}: {
  initial?: CalendarEvent
  manualSources: CalendarSource[]
  pending: boolean
  onSubmit: (value: {
    source_id?: string
    title: string
    starts_at: string
    ends_at: string
    all_day: boolean
    location: string | null
    description_md: string | null
  }) => void
  onCancel?: () => void
  /* Props 010b thêm (mở rộng tương thích-ngược, spec 010b §5.5): truyền
     `open`/`onOpenChange` thì EventForm tự bọc Dialog; không truyền thì giữ
     nguyên dạng form trần mà CalendarScreen 010a đang dùng. */
  open?: boolean
  onOpenChange?: (open: boolean) => void
  initialEvent?: CalendarEvent
  defaultDate?: string
  allowedSourceIds?: string[]
  onSuccess?: () => void
  icsWarning?: boolean
  error?: string | null
}) {
  const editTarget = initialEvent ?? initial
  const defaultDay = defaultDate ?? todayInVietnam()
  const defaultStart = `${defaultDay}T08:00`
  const sourceOptions = allowedSourceIds
    ? manualSources.filter((source) => allowedSourceIds.includes(source.id))
    : manualSources
  const [sourceId, setSourceId] = useState(
    editTarget?.source_id ?? sourceOptions[0]?.id ?? '',
  )
  const [title, setTitle] = useState(editTarget?.title ?? '')
  const [startsAt, setStartsAt] = useState(
    toVietnamDateTimeInput(editTarget?.starts_at ?? '') || defaultStart,
  )
  const [endsAt, setEndsAt] = useState(
    toVietnamDateTimeInput(editTarget?.ends_at ?? '') || `${defaultDay}T09:00`,
  )
  const [allDay, setAllDay] = useState(editTarget?.all_day ?? false)
  const [location, setLocation] = useState(editTarget?.location ?? '')
  const [description, setDescription] = useState(editTarget?.description_md ?? '')

  function submit(event: FormEvent) {
    event.preventDefault()
    const cleanTitle = title.trim()
    if (!cleanTitle || !sourceId || !startsAt || !endsAt || pending) return
    onSubmit({
      source_id: editTarget ? undefined : sourceId,
      title: cleanTitle,
      starts_at: vietnamInputToIso(startsAt),
      ends_at: vietnamInputToIso(endsAt),
      all_day: allDay,
      location: location.trim() || null,
      description_md: description.trim() || null,
    })
    onSuccess?.()
  }

  function toggleAllDay(checked: boolean) {
    setAllDay(checked)
    if (checked && startsAt) {
      const range = allDayVietnamRange(startsAt.slice(0, 10))
      setStartsAt(range.startsAt)
      setEndsAt(range.endsAt)
    }
  }

  const form = (
    <form data-testid="calendar-event-form" className="space-y-4" onSubmit={submit}>
      {!editTarget ? (
        <label className="block space-y-1.5 text-sm font-semibold">
          <span>Nguồn thủ công</span>
          <Select value={sourceId} onValueChange={setSourceId}>
            <SelectTrigger className="h-11 w-full bg-card" aria-label="Nguồn thủ công">
              <span>{sourceOptions.find((source) => source.id === sourceId)?.name ?? 'Chọn nguồn'}</span>
            </SelectTrigger>
            <SelectContent>
              {sourceOptions.map((source) => (
                <SelectItem key={source.id} value={source.id}>
                  {source.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
      ) : null}
      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Tiêu đề</span>
        <Input
          autoFocus
          className="h-11 bg-card"
          value={title}
          required
          onChange={(event) => setTitle(event.target.value)}
        />
      </label>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block space-y-1.5 text-sm font-semibold">
          <span>Bắt đầu · giờ Việt Nam</span>
          <Input
            className="h-11 bg-card"
            type="datetime-local"
            value={startsAt}
            required
            onChange={(event) => setStartsAt(event.target.value)}
          />
        </label>
        <label className="block space-y-1.5 text-sm font-semibold">
          <span>Kết thúc · giờ Việt Nam</span>
          <Input
            className="h-11 bg-card"
            type="datetime-local"
            value={endsAt}
            required
            onChange={(event) => setEndsAt(event.target.value)}
          />
        </label>
      </div>
      <label className="flex min-h-11 items-center gap-3 text-sm font-semibold">
        <Checkbox
          className="size-5 rounded-md"
          checked={allDay}
          onCheckedChange={(checked) => toggleAllDay(checked === true)}
        />
        <span>Cả ngày</span>
      </label>
      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Địa điểm</span>
        <Input className="h-11 bg-card" value={location} onChange={(event) => setLocation(event.target.value)} />
      </label>
      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Mô tả</span>
        <Textarea className="bg-card" value={description} onChange={(event) => setDescription(event.target.value)} />
      </label>
      <div className="flex flex-wrap gap-2">
        <Button size="lg" type="submit" disabled={!title.trim() || !sourceId || pending}>
          {pending ? 'Đang lưu…' : editTarget ? 'Lưu buổi' : 'Tạo buổi'}
        </Button>
        {onCancel ? (
          <Button size="lg" variant="outline" type="button" onClick={onCancel}>
            Huỷ
          </Button>
        ) : null}
      </div>
    </form>
  )

  if (open !== undefined && onOpenChange) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent
          data-testid="calendar-event-dialog"
          className="max-h-[85vh] overflow-y-auto sm:max-w-lg"
        >
          <DialogHeader>
            <DialogTitle>{editTarget ? 'Sửa buổi' : 'Tạo buổi thủ công'}</DialogTitle>
            <DialogDescription>Thời gian được hiểu theo giờ Việt Nam (+07:00).</DialogDescription>
          </DialogHeader>
          {icsWarning ? (
            <p className="text-sm text-warn">
              Buổi này thuộc nguồn nhập từ file — sửa tay sẽ mất khi nhập lại.
            </p>
          ) : null}
          {error ? (
            <p data-testid="calendar-event-error" className="text-sm text-bad" role="alert">
              {error}
            </p>
          ) : null}
          {form}
        </DialogContent>
      </Dialog>
    )
  }

  return form
}
