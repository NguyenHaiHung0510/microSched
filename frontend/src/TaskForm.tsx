import { type FormEvent, useState } from 'react'

import {
  canSubmitTask,
  type TaskFormState,
  type TaskPayload,
  type TaskPriority,
  taskPayload,
} from './task-ui.js'

type InitialTask = {
  title: string
  body_md: string | null
  priority: TaskPriority | null
  due_at: string | null
  is_private: boolean
}

const inputClass =
  'h-9 w-full rounded-md border bg-white px-3 text-sm outline-none focus:border-neutral-500'
const textareaClass =
  'min-h-20 w-full rounded-md border bg-white px-3 py-2 text-sm outline-none focus:border-neutral-500'
const primaryButtonClass =
  'h-8 rounded-lg bg-neutral-900 px-2.5 text-sm font-medium text-white disabled:pointer-events-none disabled:opacity-50'
const outlineButtonClass =
  'h-8 rounded-lg border bg-white px-2.5 text-sm font-medium disabled:pointer-events-none disabled:opacity-50'

function dueForInput(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
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
    <form className="space-y-3" onSubmit={submit}>
      <label className="block space-y-1 text-sm">
        <span>Tiêu đề</span>
        <input
          className={inputClass}
          value={title}
          minLength={1}
          required
          onChange={(event) => setTitle(event.target.value)}
        />
      </label>
      <label className="block space-y-1 text-sm">
        <span>Nội dung</span>
        <textarea
          className={textareaClass}
          value={body}
          onChange={(event) => setBody(event.target.value)}
        />
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block space-y-1 text-sm">
          <span>Ưu tiên</span>
          <select
            className={inputClass}
            value={priority}
            onChange={(event) => setPriority(event.target.value as TaskPriority | '')}
          >
            <option value="">Không đặt</option>
            <option value="p1">P1 — cao</option>
            <option value="p2">P2 — vừa</option>
            <option value="p3">P3 — thấp</option>
          </select>
        </label>
        <label className="block space-y-1 text-sm">
          <span>Hạn</span>
          <input
            className={inputClass}
            type="datetime-local"
            value={dueAt}
            onChange={(event) => setDueAt(event.target.value)}
          />
        </label>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={isPrivate}
          onChange={(event) => setIsPrivate(event.target.checked)}
        />
        Riêng tư
      </label>
      <div className="flex gap-2">
        <button
          className={primaryButtonClass}
          type="submit"
          disabled={!canSubmitTask(title, pending)}
        >
          {pending ? 'Đang lưu…' : submitLabel}
        </button>
        {onCancel ? (
          <button className={outlineButtonClass} type="button" onClick={onCancel}>
            Huỷ
          </button>
        ) : null}
      </div>
    </form>
  )
}
