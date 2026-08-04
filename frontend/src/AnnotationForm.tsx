import { type FormEvent, useState } from 'react'

import { SOURCE_COLOR_KEYS, todayInVietnam } from '@/calendar-ui'
import type { DayAnnotation } from '@/calendar-scroll'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'

export type AnnotationFormValue = {
  starts_on: string
  ends_on: string
  label: string
  note_md: string | null
  color: string | null
  is_private: boolean
}

const NO_COLOR = 'none'

export function AnnotationForm({
  initial,
  defaultStartsOn,
  privateLocked,
  pending,
  onSubmit,
  onCancel,
}: {
  initial?: DayAnnotation
  defaultStartsOn?: string
  privateLocked: boolean
  pending: boolean
  onSubmit: (value: AnnotationFormValue) => void
  onCancel?: () => void
}) {
  const defaultDay = defaultStartsOn ?? todayInVietnam()
  const [startsOn, setStartsOn] = useState(initial?.starts_on ?? defaultDay)
  const [endsOn, setEndsOn] = useState(initial?.ends_on ?? initial?.starts_on ?? defaultDay)
  const [label, setLabel] = useState(initial?.label ?? '')
  const [noteMd, setNoteMd] = useState(initial?.note_md ?? '')
  const [color, setColor] = useState(initial?.color ?? null)
  const [isPrivate, setIsPrivate] = useState(initial?.is_private ?? false)

  const rangeValid = Boolean(startsOn && endsOn && endsOn >= startsOn)
  const canSubmit = label.trim().length > 0 && rangeValid && !pending

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!canSubmit) return
    onSubmit({
      starts_on: startsOn,
      ends_on: endsOn,
      label: label.trim(),
      note_md: noteMd.trim() || null,
      color,
      is_private: isPrivate,
    })
  }

  return (
    <form data-testid="calendar-annotation-form" className="space-y-4" onSubmit={submit}>
      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Nhãn</span>
        <Input
          autoFocus
          className="h-10 bg-card"
          value={label}
          required
          maxLength={256}
          placeholder="Ví dụ: Về quê"
          onChange={(event) => setLabel(event.target.value)}
        />
      </label>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block space-y-1.5 text-sm font-semibold">
          <span>Bắt đầu</span>
          <Input
            className="h-10 bg-card"
            type="date"
            value={startsOn}
            required
            onChange={(event) => setStartsOn(event.target.value)}
          />
        </label>
        <label className="block space-y-1.5 text-sm font-semibold">
          <span>Kết thúc</span>
          <Input
            className="h-10 bg-card"
            type="date"
            value={endsOn}
            min={startsOn}
            required
            onChange={(event) => setEndsOn(event.target.value)}
          />
        </label>
      </div>

      <div className="space-y-1.5 text-sm font-semibold">
        <span>Màu</span>
        <Select
          value={color ?? NO_COLOR}
          onValueChange={(value) => setColor(value === NO_COLOR ? null : value)}
        >
          <SelectTrigger className="h-10 w-full bg-card" aria-label="Màu dấu ngày">
            <span>{color ?? 'Không màu'}</span>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NO_COLOR}>Không màu</SelectItem>
            {SOURCE_COLOR_KEYS.map((key) => (
              <SelectItem key={key} value={key}>
                {key}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Ghi chú</span>
        <Textarea
          className="min-h-24 bg-card font-normal"
          value={noteMd}
          onChange={(event) => setNoteMd(event.target.value)}
        />
      </label>

      <label className="flex min-h-9 items-center gap-3 text-sm font-semibold">
        <Checkbox
          className="size-5 rounded-md"
          checked={isPrivate}
          disabled={privateLocked}
          onCheckedChange={(checked) => setIsPrivate(checked === true)}
        />
        <span>Riêng tư</span>
      </label>
      {privateLocked ? (
        <p className="text-sm text-muted-foreground">Mở khoá riêng tư để đặt.</p>
      ) : null}

      <div className="flex flex-wrap gap-2 pt-1">
        <Button size="lg" type="submit" disabled={!canSubmit}>
          {pending ? 'Đang lưu…' : initial ? 'Lưu dấu ngày' : 'Thêm dấu ngày'}
        </Button>
        {onCancel ? (
          <Button size="lg" variant="outline" type="button" onClick={onCancel}>
            Huỷ
          </Button>
        ) : null}
      </div>
    </form>
  )
}
