import { useState } from 'react'
import { Check } from 'lucide-react'

import type { CalendarEvent } from '@/calendar-ui'
import {
  mergeDayChips,
  sourceTone,
  type DayAnnotation,
  type TaskSummary,
} from '@/calendar-scroll'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export type DropTaskPayload =
  | { kind: 'quick-new-task'; title: string }
  | { kind: 'reschedule-task'; taskId: string; fromDay?: string }

export function DayCell({
  day,
  isToday,
  isOtherMonth,
  events,
  tasks,
  annotations,
  chipLimit,
  showAnnotationLabels,
  sourceColorOf,
  onSelect,
  isDesktop = false,
  onToggleTask,
  onDropTask,
}: {
  day: string
  isToday: boolean
  isOtherMonth: boolean
  events: CalendarEvent[]
  tasks: TaskSummary[]
  annotations: DayAnnotation[]
  chipLimit: number
  showAnnotationLabels: boolean
  sourceColorOf: (sourceId: string) => string | null
  onSelect: (day: string) => void
  isDesktop?: boolean
  onToggleTask?: (taskId: string, newStatus: 'open' | 'completed') => void
  onDropTask?: (day: string, payload: DropTaskPayload) => void
}) {
  const [isDragOver, setIsDragOver] = useState(false)
  const merged = mergeDayChips(events, tasks, chipLimit)
  const visibleAnnotations = annotations.slice(0, 2)
  const hiddenAnnotations = Math.max(0, annotations.length - 2)
  const dayNumber = Number(day.slice(8, 10))

  function handleDragOver(e: React.DragEvent) {
    if (!isDesktop) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
    if (!isDragOver) setIsDragOver(true)
  }

  function handleDragLeave() {
    setIsDragOver(false)
  }

  function handleDrop(e: React.DragEvent) {
    if (!isDesktop) return
    e.preventDefault()
    setIsDragOver(false)
    const raw = e.dataTransfer.getData('application/json') || e.dataTransfer.getData('text/plain')
    if (!raw || !onDropTask) return
    try {
      const payload = JSON.parse(raw) as DropTaskPayload
      if (payload.kind === 'quick-new-task' || payload.kind === 'reschedule-task') {
        onDropTask(day, payload)
      }
    } catch {
      // Ignored if non-json drag
    }
  }

  return (
    <Button
      data-testid="calendar-day-cell"
      data-day={day}
      variant="ghost"
      onClick={() => onSelect(day)}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
     className={cn(
       'flex h-auto min-h-16 w-full flex-col items-stretch justify-start gap-0.5 rounded-lg border p-1 text-left transition-colors sm:min-h-24 md:min-h-28',
        isToday ? 'border-primary bg-accent' : 'border-border/60 hover:border-primary/50',
       isDragOver && 'border-primary bg-primary/10 ring-2 ring-primary/30',
     )}
    >
      <div className="flex flex-col gap-0.5">
        {visibleAnnotations.map((annotation) => (
          <span
            data-testid="calendar-day-annotation"
            key={annotation.id}
            style={sourceTone(annotation.color)}
            className={cn(
              'block truncate rounded-sm px-1 py-px text-xs font-semibold',
              !showAnnotationLabels && 'min-h-1.5 py-0',
            )}
          >
            {showAnnotationLabels ? annotation.label : null}
          </span>
        ))}
        {hiddenAnnotations > 0 ? (
          <span className="px-1 text-xs font-semibold text-muted-foreground">
            +{hiddenAnnotations}
          </span>
        ) : null}
      </div>

      <span
        className={cn(
          'text-sm font-bold',
          isToday
            ? 'text-accent-foreground'
            : isOtherMonth
              ? 'text-muted-foreground'
              : 'text-foreground',
        )}
      >
        {dayNumber}
      </span>

      <div className="flex flex-col gap-0.5">
        {merged.chips.map((chip) =>
          chip.kind === 'event' ? (
            <span
              data-testid="calendar-day-chip-event"
              key={chip.event.id}
              style={sourceTone(sourceColorOf(chip.event.source_id))}
              className="block truncate rounded-sm px-1 py-px text-xs font-bold"
            >
              {chip.event.title}
            </span>
          ) : isDesktop ? (
            <div
              data-testid="calendar-day-chip-task"
              key={chip.task.id}
              draggable={isDesktop}
              onDragStart={(e) => {
                if (!isDesktop) return
                e.stopPropagation()
                e.dataTransfer.setData(
                  'application/json',
                  JSON.stringify({
                    kind: 'reschedule-task',
                    taskId: chip.task.id,
                    fromDay: day,
                  }),
                )
                e.dataTransfer.effectAllowed = 'move'
              }}
              className={cn(
                'group flex items-center justify-between gap-1 rounded-sm border border-dashed border-input bg-card/60 px-1 py-0.5 text-xs font-semibold text-secondary-foreground hover:border-primary',
                chip.task.status === 'completed' && 'line-through',
              )}
            >
              <span
                className={cn(
                  'min-w-0 flex-1 truncate',
                  chip.task.status === 'completed' && 'line-through',
                )}
              >
                {chip.task.title}
              </span>
              {onToggleTask ? (
                <span
                  role="checkbox"
                  aria-checked={chip.task.status === 'completed'}
                  data-testid="calendar-chip-task-toggle"
                  aria-label={`Đổi trạng thái ${chip.task.title}`}
                  onClick={(e) => {
                    e.stopPropagation()
                    onToggleTask(
                      chip.task.id,
                      chip.task.status === 'completed' ? 'open' : 'completed',
                    )
                  }}
                  className={cn(
                    'flex size-3.5 shrink-0 items-center justify-center rounded border border-input transition-colors hover:border-primary',
                    chip.task.status === 'completed'
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'bg-background',
                  )}
                >
                  {chip.task.status === 'completed' ? (
                    <Check className="size-2.5 stroke-[3]" />
                  ) : null}
                </span>
              ) : null}
            </div>
          ) : (
            <span
              data-testid="calendar-day-chip-task"
              key={chip.task.id}
              className={cn(
                'block truncate rounded-sm border border-dashed border-input px-1 py-px text-xs font-semibold text-secondary-foreground',
                chip.task.status === 'completed' && 'line-through',
              )}
            >
              {chip.task.title}
            </span>
          ),
        )}
        {merged.overflow > 0 ? (
          <span
            data-testid="calendar-day-overflow"
            className="px-1 text-xs font-semibold text-muted-foreground"
          >
            +{merged.overflow}
          </span>
        ) : null}
      </div>
    </Button>
  )
}
