import { type FormEvent, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import {
  canSubmitTask,
  type TaskDuePrecision,
  type TaskFormState,
  type TaskWritePayload,
  type TaskPriority,
  taskPayload,
  transitionTaskDuePrecision,
} from '@/task-ui'
import { todayInVietnam, toVietnamDateTimeInput } from '@/calendar-ui'

type InitialTask = {
  title: string
  body_md: string | null
  priority: TaskPriority | null
  due_precision: TaskDuePrecision
  due_on: string | null
  due_at: string | null
  is_private: boolean
}

const priorityLabels: Record<TaskPriority, string> = {
  p1: 'P1',
  p2: 'P2',
  p3: 'P3',
}

const duePrecisionLabels: Record<TaskDuePrecision, string> = {
  date: 'Ngày',
  datetime: 'Ngày + giờ',
  none: 'Chưa xếp lịch',
}

function initialDue(initial?: InitialTask): { precision: TaskDuePrecision; day: string; time: string } {
  if (!initial) return { precision: 'date', day: todayInVietnam(), time: '' }
  if (initial.due_precision === 'date') {
    return { precision: 'date', day: initial.due_on ?? '', time: '' }
  }
  if (initial.due_precision === 'datetime') {
    const local = toVietnamDateTimeInput(initial.due_at)
    const [day = '', time = ''] = local.split('T')
    return { precision: 'datetime', day, time }
  }
  return { precision: 'none', day: '', time: '' }
}

function selectedPriorityLabel(priority: TaskPriority | ''): string {
  return priority ? priorityLabels[priority] : 'Không đặt'
}

export function TaskForm({
  initial,
  submitLabel,
  pending,
  onSubmit,
  onCancel,
}: {
  initial?: InitialTask
  submitLabel: string
  pending: boolean
  onSubmit: (payload: TaskWritePayload) => void
  onCancel?: () => void
}) {
  const [title, setTitle] = useState(initial?.title ?? '')
  const [body, setBody] = useState(initial?.body_md ?? '')
  const [priority, setPriority] = useState<TaskPriority | ''>(initial?.priority ?? '')
  const dueInitial = initialDue(initial)
  const [duePrecision, setDuePrecision] = useState<TaskDuePrecision>(dueInitial.precision)
  const [dueOn, setDueOn] = useState(dueInitial.day)
  const [dueTime, setDueTime] = useState(dueInitial.time)
  const [isPrivate, setIsPrivate] = useState(initial?.is_private ?? false)

  function submit(event: FormEvent) {
    event.preventDefault()
    const state: TaskFormState = {
      title,
      body,
      priority,
      duePrecision,
      dueOn,
      dueTime,
      isPrivate,
    }
    onSubmit(taskPayload(state))
  }

  function changeDuePrecision(value: string) {
    const next = value as TaskDuePrecision
    const schedule = transitionTaskDuePrecision(
      { duePrecision, dueOn, dueTime },
      next,
      todayInVietnam(),
    )
    setDuePrecision(schedule.duePrecision)
    setDueOn(schedule.dueOn)
    setDueTime(schedule.dueTime)
  }

  return (
    <form className="space-y-4" onSubmit={submit}>
      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Tiêu đề</span>
        <Input
          className="h-11 bg-card"
          value={title}
          minLength={1}
          required
          onChange={(event) => setTitle(event.target.value)}
        />
      </label>

      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Nội dung</span>
        <Textarea
          className="min-h-24 bg-card font-normal"
          value={body}
          onChange={(event) => setBody(event.target.value)}
        />
      </label>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <span className="text-sm font-semibold">Ưu tiên</span>
          <Select
            value={priority || 'none'}
            onValueChange={(value) =>
              setPriority(value === 'none' ? '' : (value as TaskPriority))
            }
          >
            <SelectTrigger size="lg" className="w-full bg-card" aria-label="Ưu tiên">
              <span data-selected-priority={priority || 'none'}>
                {selectedPriorityLabel(priority)}
              </span>
            </SelectTrigger>
            <SelectContent position="popper" align="start">
              <SelectItem value="none">Không đặt</SelectItem>
              <SelectItem value="p1">{priorityLabels.p1}</SelectItem>
              <SelectItem value="p2">{priorityLabels.p2}</SelectItem>
              <SelectItem value="p3">{priorityLabels.p3}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <span className="text-sm font-semibold">Lịch</span>
          <Select value={duePrecision} onValueChange={changeDuePrecision}>
            <SelectTrigger size="lg" className="w-full bg-card" aria-label="Kiểu lịch">
              <span data-selected-due-precision={duePrecision}>
                {duePrecisionLabels[duePrecision]}
              </span>
            </SelectTrigger>
            <SelectContent position="popper" align="start">
              <SelectItem value="date">Ngày</SelectItem>
              <SelectItem value="datetime">Ngày + giờ</SelectItem>
              <SelectItem value="none">Chưa xếp lịch</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {duePrecision !== 'none' ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block space-y-1.5 text-sm font-semibold">
            <span>Ngày</span>
            <Input className="h-11 bg-card" type="date" value={dueOn} onChange={(event) => setDueOn(event.target.value)} />
          </label>
          {duePrecision === 'datetime' ? (
            <label className="block space-y-1.5 text-sm font-semibold">
              <span>Giờ</span>
              <Input className="h-11 bg-card" type="time" value={dueTime} onChange={(event) => setDueTime(event.target.value)} />
            </label>
          ) : null}
        </div>
      ) : null}
      {duePrecision === 'datetime' && !dueTime ? (
        <p className="text-sm text-muted-foreground" role="status">Chọn giờ để lưu task có giờ.</p>
      ) : null}

      <label className="flex min-h-11 items-center gap-3 text-sm font-semibold">
        <Checkbox
          className="size-5 rounded-md"
          checked={isPrivate}
          onCheckedChange={(checked) => setIsPrivate(checked === true)}
        />
        <span>Riêng tư</span>
      </label>

      <div className="flex flex-wrap gap-2 pt-1">
        <Button
          size="lg"
          type="submit"
          disabled={!canSubmitTask(title, pending, { duePrecision, dueOn, dueTime })}
        >
          {pending ? 'Đang lưu…' : submitLabel}
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
