import { type ReactElement, useState } from 'react'
import { Check, Square } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { VIETNAM_TIME_ZONE } from '@/calendar-ui'
import type { TaskPriority, TaskSchedule } from '@/task-ui'

export type TaskPreviewData = TaskSchedule & {
  id: string
  body_md?: string | null
  priority?: TaskPriority | null
  items?: Array<{ id: string; content: string; is_completed: boolean }>
}

function dueLabel(task: TaskSchedule): string | null {
  if (task.due_precision === 'date' && task.due_on) return task.due_on.split('-').reverse().join('/')
  if (task.due_precision === 'datetime' && task.due_at) {
    return new Intl.DateTimeFormat('vi-VN', {
      timeZone: VIETNAM_TIME_ZONE, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    }).format(new Date(task.due_at))
  }
  return null
}

const priorities: Record<TaskPriority, string> = { p1: 'Ưu tiên cao', p2: 'Ưu tiên vừa', p3: 'Ưu tiên thấp' }

export function TaskPreviewContent({ task }: { task: TaskPreviewData }) {
  const items = task.items ?? []
  const due = dueLabel(task)
  const metadata = [due, task.priority ? priorities[task.priority] : null].filter(Boolean).join(' · ')
  return <div data-testid="task-preview-content" className="space-y-3 text-left text-sm leading-relaxed">
    {metadata ? <p data-testid="task-preview-metadata" className="text-xs font-semibold text-primary">{metadata}</p> : null}
    {task.body_md?.trim() ? <section className="space-y-1" data-testid="task-preview-body">
      <p className="text-xs font-bold text-primary">Nội dung</p>
      <p className="whitespace-pre-wrap [overflow-wrap:anywhere]">{task.body_md}</p>
    </section> : null}
    {items.length ? <section data-testid="task-preview-checklist" className={`space-y-2 ${task.body_md?.trim() ? 'border-t border-border/30 pt-3' : ''}`}>
      <p className="text-xs font-bold text-primary">Checklist · {items.filter(item => item.is_completed).length}/{items.length} đã xong</p>
      <ul className="space-y-2">{items.map(item => <li key={item.id} data-testid="task-preview-item" className="flex items-start gap-2">
        {item.is_completed ? <Check aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-primary" /> : <Square aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted-foreground" />}
        <span className="sr-only">{item.is_completed ? 'Đã xong: ' : 'Chưa xong: '}</span>
        <span className={item.is_completed ? 'min-w-0 text-muted-foreground line-through [overflow-wrap:anywhere]' : 'min-w-0 [overflow-wrap:anywhere]'}>{item.content}</span>
      </li>)}</ul>
    </section> : null}
  </div>
}

/** No extra layout wrapper or fetch: the original title/chip keeps its actions. */
export function TaskPreview({ task, disabled = false, children }: { task: TaskPreviewData; disabled?: boolean; children: ReactElement }) {
  const [open, setOpen] = useState(false)
  const hasPreview = Boolean(task.body_md?.trim() || task.items?.length || dueLabel(task) || task.priority)
  return <TooltipProvider delayDuration={180}><Tooltip open={open && !disabled && hasPreview} onOpenChange={setOpen}>
    <TooltipTrigger asChild onPointerDownCapture={() => setOpen(false)} onDragStartCapture={() => setOpen(false)}>{children}</TooltipTrigger>
    <TooltipContent data-testid="task-preview" data-task-id={task.id} side="top" sideOffset={8} collisionPadding={12}
      className="w-[min(360px,calc(100vw-24px))] max-w-none overflow-hidden rounded-xl border border-primary/30 bg-card p-4 text-foreground shadow-2"
      onClick={event => event.stopPropagation()} onPointerDown={event => event.stopPropagation()}>
      <div className="max-h-[min(320px,55dvh,var(--radix-tooltip-content-available-height))] overflow-y-auto overscroll-contain" data-testid="task-preview-scroll">
        <TaskPreviewContent task={task} />
      </div>
    </TooltipContent>
  </Tooltip></TooltipProvider>
}
