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
  type TaskFormState,
  type TaskPayload,
  type TaskPriority,
  taskPayload,
} from '@/task-ui'

type InitialTask = {
  title: string
  body_md: string | null
  priority: TaskPriority | null
  due_at: string | null
  is_private: boolean
}

const priorityLabels: Record<TaskPriority, string> = {
  p1: 'P1',
  p2: 'P2',
  p3: 'P3',
}

function dueForInput(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
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
  onSubmit: (payload: TaskPayload) => void
  onCancel?: () => void
}) {
  const [title, setTitle] = useState(initial?.title ?? '')
  const [body, setBody] = useState(initial?.body_md ?? '')
  const [priority, setPriority] = useState<TaskPriority | ''>(initial?.priority ?? '')
  const [dueAt, setDueAt] = useState(dueForInput(initial?.due_at ?? null))
  const [isPrivate, setIsPrivate] = useState(initial?.is_private ?? false)

  function submit(event: FormEvent) {
    event.preventDefault()
    const state: TaskFormState = {
      title,
      body,
      priority,
      dueAt,
      isPrivate,
    }
    onSubmit(taskPayload(state))
  }

  return (
    <form className="space-y-4" onSubmit={submit}>
      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Tiêu đề</span>
        <Input
          className="h-10 bg-card"
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
            <SelectTrigger className="h-10 w-full bg-card" aria-label="Ưu tiên">
              <span data-selected-priority={priority || 'none'}>
                {selectedPriorityLabel(priority)}
              </span>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">Không đặt</SelectItem>
              <SelectItem value="p1">{priorityLabels.p1}</SelectItem>
              <SelectItem value="p2">{priorityLabels.p2}</SelectItem>
              <SelectItem value="p3">{priorityLabels.p3}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <label className="block space-y-1.5 text-sm font-semibold">
          <span>Hạn</span>
          <Input
            className="h-10 bg-card"
            type="datetime-local"
            value={dueAt}
            onChange={(event) => setDueAt(event.target.value)}
          />
        </label>
      </div>

      <label className="flex min-h-9 items-center gap-3 text-sm font-semibold">
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
          disabled={!canSubmitTask(title, pending)}
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
