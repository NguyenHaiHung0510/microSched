import type { CalendarEvent } from '@/calendar-ui'
import {
  mergeDayChips,
  sourceTone,
  type DayAnnotation,
  type TaskSummary,
} from '@/calendar-scroll'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

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
}) {
  const merged = mergeDayChips(events, tasks, chipLimit)
  const visibleAnnotations = annotations.slice(0, 2)
  const hiddenAnnotations = Math.max(0, annotations.length - 2)
  const dayNumber = Number(day.slice(8, 10))

  return (
    <Button
      data-testid="calendar-day-cell"
      data-day={day}
      variant="ghost"
      onClick={() => onSelect(day)}
      className={cn(
        'flex h-auto min-h-16 w-full flex-col items-stretch justify-start gap-0.5 rounded-lg border p-1 text-left sm:min-h-24',
        // Hôm nay: viền đậm + nền accent nhạt, đúng hình dạng app cũ.
        isToday ? 'border-primary bg-accent' : 'border-transparent',
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
