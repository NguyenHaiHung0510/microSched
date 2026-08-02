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
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'

export function EventForm({
  initial,
  manualSources,
  pending,
  onSubmit,
  onCancel,
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
  onCancel: () => void
}) {
  const defaultStart = `${todayInVietnam()}T08:00`
  const [sourceId, setSourceId] = useState(initial?.source_id ?? manualSources[0]?.id ?? '')
  const [title, setTitle] = useState(initial?.title ?? '')
  const [startsAt, setStartsAt] = useState(toVietnamDateTimeInput(initial?.starts_at ?? '') || defaultStart)
  const [endsAt, setEndsAt] = useState(
    toVietnamDateTimeInput(initial?.ends_at ?? '') || `${todayInVietnam()}T09:00`,
  )
  const [allDay, setAllDay] = useState(initial?.all_day ?? false)
  const [location, setLocation] = useState(initial?.location ?? '')
  const [description, setDescription] = useState(initial?.description_md ?? '')

  function submit(event: FormEvent) {
    event.preventDefault()
    const cleanTitle = title.trim()
    if (!cleanTitle || !sourceId || !startsAt || !endsAt || pending) return
    onSubmit({
      source_id: initial ? undefined : sourceId,
      title: cleanTitle,
      starts_at: vietnamInputToIso(startsAt),
      ends_at: vietnamInputToIso(endsAt),
      all_day: allDay,
      location: location.trim() || null,
      description_md: description.trim() || null,
    })
  }

  function toggleAllDay(checked: boolean) {
    setAllDay(checked)
    if (checked && startsAt) {
      const range = allDayVietnamRange(startsAt.slice(0, 10))
      setStartsAt(range.startsAt)
      setEndsAt(range.endsAt)
    }
  }

  return (
    <form data-testid="calendar-event-form" className="space-y-4" onSubmit={submit}>
      {!initial ? (
        <label className="block space-y-1.5 text-sm font-semibold">
          <span>Nguồn thủ công</span>
          <Select value={sourceId} onValueChange={setSourceId}>
            <SelectTrigger className="h-11 w-full bg-card" aria-label="Nguồn thủ công">
              <span>{manualSources.find((source) => source.id === sourceId)?.name ?? 'Chọn nguồn'}</span>
            </SelectTrigger>
            <SelectContent>
              {manualSources.map((source) => (
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
          {pending ? 'Đang lưu…' : initial ? 'Lưu buổi' : 'Tạo buổi'}
        </Button>
        <Button size="lg" variant="outline" type="button" onClick={onCancel}>
          Huỷ
        </Button>
      </div>
    </form>
  )
}
