import { ChevronLeft, ChevronRight } from 'lucide-react'

import {
  WEEKDAY_LABELS,
  addMonths,
  monthKey,
  monthLabel,
  monthWeeks,
  type YearMonth,
} from '@/calendar-scroll'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function MiniNav({
  anchor,
  visibleDays,
  onSelectDay,
  onPrev,
  onNext,
}: {
  anchor: YearMonth
  visibleDays: Set<string>
  onSelectDay: (day: string) => void
  onPrev: () => void
  onNext: () => void
}) {
  const months: YearMonth[] = [anchor, addMonths(anchor.year, anchor.month, 1)]

  return (
    <aside
      data-testid="calendar-mininav"
      className="hidden w-52 shrink-0 flex-col gap-4 sm:flex"
      aria-label="Lịch thu nhỏ"
    >
      <div className="flex items-center justify-between gap-2">
        <Button
          data-testid="calendar-mininav-prev"
          size="icon-lg"
          variant="outline"
          aria-label="Tháng trước"
          onClick={onPrev}
        >
          <ChevronLeft />
        </Button>
        <Button
          data-testid="calendar-mininav-next"
          size="icon-lg"
          variant="outline"
          aria-label="Tháng sau"
          onClick={onNext}
        >
          <ChevronRight />
        </Button>
      </div>

      {months.map(({ year, month }) => {
        const blockKey = monthKey(year, month)
        return (
          <div key={blockKey} className="space-y-1">
            <p className="text-sm font-bold">{monthLabel(year, month)}</p>
            <div className="grid grid-cols-7 gap-0.5 text-center">
              {WEEKDAY_LABELS.map((label) => (
                <span key={label} className="text-xs text-muted-foreground">
                  {label}
                </span>
              ))}
              {monthWeeks(year, month).flatMap((week) =>
                week.days.map((day) => {
                  const inBlock = day.slice(0, 7) === blockKey
                  const active = visibleDays.has(day)
                  return inBlock ? (
                    <Button
                      data-testid="calendar-mininav-day"
                      data-day={day}
                      key={day}
                      variant="ghost"
                      aria-label={day}
                      onClick={() => onSelectDay(day)}
                      className={cn(
                        // Đích chạm tối thiểu 24×24 theo qa-framework.md:71.
                        'h-6 min-w-6 rounded p-0 text-xs',
                        active &&
                          'bg-accent text-accent-foreground hover:bg-accent hover:text-accent-foreground',
                      )}
                    >
                      {Number(day.slice(8, 10))}
                    </Button>
                  ) : (
                    <span key={day} aria-hidden="true" />
                  )
                }),
              )}
            </div>
          </div>
        )
      })}
    </aside>
  )
}
