import { type FormEvent, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  type ReminderAction,
  type ReminderMode,
  type Tracker,
  type TrackerDirection,
  type TrackerGroup,
  type TrackerInputMode,
  type TrackerKind,
} from '@/tracker-ui'

export type TrackerWritePayload = {
  name: string
  kind: TrackerKind
  direction: TrackerDirection
  input_mode: TrackerInputMode
  group_id: string | null
  unit: string | null
  is_private: boolean
  reminder_time?: string | null
  reminder_text?: string | null
  reminder_mode?: ReminderMode | null
  reminder_interval_days?: number | null
  reminder_action?: ReminderAction | null
  ensure_push?: boolean
}

export function TrackerForm({
  initial,
  groups,
  pending,
  privateLocked,
  onSubmit,
  onCancel,
}: {
  initial?: Tracker | null
  groups: TrackerGroup[]
  pending: boolean
  privateLocked: boolean
  onSubmit: (payload: TrackerWritePayload) => void
  onCancel?: () => void
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [kind, setKind] = useState<TrackerKind>(initial?.kind ?? 'health')
  const [inputMode, setInputMode] = useState<TrackerInputMode>(initial?.input_mode ?? 'event')
  const [direction, setDirection] = useState<TrackerDirection>(initial?.direction ?? 'out')
  const [groupId, setGroupId] = useState<string>(initial?.group_id ?? '')
  const [unit, setUnit] = useState(initial?.unit ?? '')
  const [isPrivate, setIsPrivate] = useState(initial?.is_private ?? false)
  const [reminderEnabled, setReminderEnabled] = useState(Boolean(initial?.reminder_time))
  const [reminderMode, setReminderMode] = useState<ReminderMode>(initial?.reminder_mode ?? 'fixed')
  const [reminderIntervalDays, setReminderIntervalDays] = useState<string>(
    String(initial?.reminder_interval_days ?? 1),
  )
  const [reminderAction, setReminderAction] = useState<ReminderAction>(
    initial?.reminder_action ?? (initial?.input_mode === 'event' || !initial ? 'confirm_event' : 'open_tracker'),
  )
  const [reminderTime, setReminderTime] = useState(initial?.reminder_time ?? '08:00')
  const [reminderText, setReminderText] = useState(initial?.reminder_text ?? '')

  const kindGroups = groups.filter((group) => group.kind === kind)
  const needsUnit = inputMode === 'quantity'
  const canSubmit = name.trim().length > 0 && (!needsUnit || unit.trim().length > 0) && !pending

  function handleKindChange(newKind: TrackerKind) {
    setKind(newKind)
    const validGroups = groups.filter((g) => g.kind === newKind)
    if (groupId && !validGroups.some((g) => g.id === groupId)) {
      setGroupId('')
    }
  }

  function handleInputModeChange(newInputMode: TrackerInputMode) {
    setInputMode(newInputMode)
    if (newInputMode === 'money' || newInputMode === 'quantity') {
      setReminderAction('open_tracker')
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!canSubmit) return
    const intervalNum = Math.max(1, parseInt(reminderIntervalDays, 10) || 1)
    const effectiveAction: ReminderAction =
      inputMode === 'event' ? reminderAction : 'open_tracker'
    const reminderPayload = reminderEnabled
      ? {
          reminder_mode: reminderMode,
          reminder_interval_days: intervalNum,
          reminder_action: effectiveAction,
          reminder_time: reminderTime,
          reminder_text: reminderText.trim() || null,
          ensure_push: true,
        }
      : {
          reminder_mode: null,
          reminder_interval_days: null,
          reminder_action: null,
          reminder_time: null,
          reminder_text: null,
          ensure_push: false,
        }
    onSubmit({
      name: name.trim(),
      kind,
      direction,
      input_mode: inputMode,
      group_id: groupId || null,
      unit: needsUnit ? unit.trim() : null,
      is_private: isPrivate,
      ...reminderPayload,
    })
  }

  return (
    <form data-testid="tracker-form" className="space-y-4" onSubmit={submit}>
      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Tên tracker</span>
        <Input
          data-testid="tracker-name-input"
          className="h-10 bg-card"
          value={name}
          maxLength={150}
          onChange={(event) => setName(event.target.value)}
        />
      </label>

      <div className="grid grid-cols-2 gap-3">
        <label className="block space-y-1.5 text-sm font-semibold">
          <span>Loại</span>
          <Select value={kind} onValueChange={(value) => handleKindChange(value as TrackerKind)}>
            <SelectTrigger className="w-full bg-card">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="health">Sức khoẻ</SelectItem>
              <SelectItem value="finance">Tài chính</SelectItem>
              <SelectItem value="general">Chung</SelectItem>
            </SelectContent>
          </Select>
        </label>
        <label className="block space-y-1.5 text-sm font-semibold">
          <span>Cách ghi</span>
          <Select
            value={inputMode}
            onValueChange={(value) => handleInputModeChange(value as TrackerInputMode)}
          >
            <SelectTrigger className="w-full bg-card">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="event">Một chạm</SelectItem>
              <SelectItem value="money">Số tiền</SelectItem>
              <SelectItem value="quantity">Số lượng</SelectItem>
            </SelectContent>
          </Select>
        </label>
      </div>

      {inputMode === 'money' ? (
        <label className="block space-y-1.5 text-sm font-semibold">
          <span>Chiều tiền</span>
          <Select value={direction} onValueChange={(value) => setDirection(value as TrackerDirection)}>
            <SelectTrigger className="w-full bg-card">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="out">Chi ra</SelectItem>
              <SelectItem value="in">Thu vào</SelectItem>
            </SelectContent>
          </Select>
        </label>
      ) : null}

      {needsUnit ? (
        <label className="block space-y-1.5 text-sm font-semibold">
          <span>Đơn vị</span>
          <Input
            className="h-10 bg-card"
            value={unit}
            placeholder="ví dụ: phút, lon, km"
            onChange={(event) => setUnit(event.target.value)}
          />
        </label>
      ) : null}

      <fieldset className="space-y-3 rounded-lg border border-input p-3">
        <legend className="px-1 text-sm font-semibold">Nhắc nhở</legend>
        <label className="flex min-h-11 items-center gap-3 text-sm font-semibold">
          <Checkbox
            className="size-5 rounded-md"
            data-testid="tracker-reminder-enabled"
            checked={reminderEnabled}
            onCheckedChange={(checked) => setReminderEnabled(checked === true)}
          />
          <span>Bật nhắc nhở</span>
        </label>
        {reminderEnabled ? (
          <>
            <div className="grid grid-cols-2 gap-3">
              <label className="block space-y-1.5 text-sm font-semibold">
                <span>Kiểu nhắc</span>
                <Select
                  value={reminderMode}
                  onValueChange={(value) => setReminderMode(value as ReminderMode)}
                >
                  <SelectTrigger data-testid="tracker-reminder-mode" className="w-full bg-card">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="fixed">Theo lịch cố định</SelectItem>
                    <SelectItem value="after_entry">Sau lần ghi gần nhất</SelectItem>
                  </SelectContent>
                </Select>
              </label>
              <label className="block space-y-1.5 text-sm font-semibold">
                <span>{reminderMode === 'fixed' ? 'Mỗi N ngày' : 'Nhắc sau N ngày chưa ghi'}</span>
                <Input
                  data-testid="tracker-reminder-interval"
                  className="h-10 bg-card"
                  type="number"
                  min="1"
                  step="1"
                  value={reminderIntervalDays}
                  onChange={(event) => setReminderIntervalDays(event.target.value)}
                />
              </label>
            </div>
            <label className="block space-y-1.5 text-sm font-semibold">
              <span>Giờ nhắc</span>
              <Input
                className="h-10 bg-card"
                data-testid="tracker-reminder-time"
                type="time"
                value={reminderTime}
                onChange={(event) => setReminderTime(event.target.value)}
              />
            </label>
            {inputMode === 'event' ? (
              <label className="block space-y-1.5 text-sm font-semibold">
                <span>Hành động khi bấm nhắc</span>
                <Select
                  value={reminderAction}
                  onValueChange={(value) => setReminderAction(value as ReminderAction)}
                >
                  <SelectTrigger data-testid="tracker-reminder-action" className="w-full bg-card">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="confirm_event">Xác nhận và ghi một chạm</SelectItem>
                    <SelectItem value="open_tracker">Mở tracker để ghi</SelectItem>
                  </SelectContent>
                </Select>
              </label>
            ) : (
              <div className="space-y-1.5 text-sm font-semibold">
                <span>Hành động khi bấm nhắc</span>
                <div className="rounded-md border border-input bg-muted/40 p-2.5 text-xs font-normal text-muted-foreground">
                  Mở tracker để nhập số liệu
                </div>
              </div>
            )}
            <label className="block space-y-1.5 text-sm font-semibold">
              <span>Nội dung hiện trên màn hình khoá (không bắt buộc)</span>
              <Input
                className="h-10 bg-card"
                data-testid="tracker-reminder-text"
                value={reminderText}
                maxLength={240}
                onChange={(event) => setReminderText(event.target.value)}
              />
              <span className="block text-xs font-normal text-muted-foreground">
                Nội dung này hiển thị công khai trên màn hình khoá thiết bị.
              </span>
            </label>
          </>
        ) : null}
      </fieldset>

      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Nhóm</span>
        <Select value={groupId} onValueChange={setGroupId}>
          <SelectTrigger className="w-full bg-card">
            <SelectValue placeholder="Chưa nhóm" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">Chưa nhóm</SelectItem>
            {kindGroups.map((group) => (
              <SelectItem key={group.id} value={group.id}>
                {group.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
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
        <p className="text-xs text-muted-foreground">
          Đang khoá riêng tư — chưa tạo được tracker riêng tư cho tới khi mở khoá.
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2 pt-1">
        <Button size="lg" className="min-h-11" type="submit" disabled={!canSubmit}>
          {pending ? 'Đang lưu…' : initial ? 'Lưu thay đổi' : 'Tạo tracker'}
        </Button>
        {onCancel ? (
          <Button size="lg" variant="outline" className="min-h-11" type="button" onClick={onCancel}>
            Huỷ
          </Button>
        ) : null}
      </div>
    </form>
  )
}
