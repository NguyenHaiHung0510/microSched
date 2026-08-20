import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueries } from '@tanstack/react-query'

import { apiRequest } from '@/api'
import { todayInVietnam, type CalendarEvent, type CalendarSource } from '@/calendar-ui'
import {
  CHIP_LIMIT_DESKTOP,
  CHIP_LIMIT_MOBILE,
  WEEKDAY_LABELS,
  addMonths,
  annotationsByDay,
  dedupeById,
  eventsByDay,
  lastDayOfMonth,
  monthFetchRange,
  monthKey,
  monthLabel,
  monthWeeks,
  monthsWindow,
  tasksByDueDay,
  visibleDayKeys,
  type CalendarTask,
  type DayAnnotation,
  type YearMonth,
} from '@/calendar-scroll'
import {
  annotationsQuerySpec,
  calendarTasksQuerySpec,
  monthEventsQuerySpec,
  sessionQuerySpec,
  sourcesQuerySpec,
} from '@/calendar-queries'
import { DayCell } from '@/DayCell'
import { DayDetailDialog } from '@/DayDetailDialog'
import { MiniNav } from '@/MiniNav'
import { Button } from '@/components/ui/button'
import { remainingSeconds } from '@/private-gate'

type Envelope<T> = { items: T[] }
type SessionLite = { private_until: string | null }

const HEADER_HEIGHT = 56
const EDGE_EXTEND_PX = 80
const EXTEND_MONTHS = 6

async function getSources(): Promise<Envelope<CalendarSource>> {
  return apiRequest<Envelope<CalendarSource>>('/api/calendar/sources')
}

async function getMonthEvents(year: number, month: number): Promise<Envelope<CalendarEvent>> {
  const range = monthFetchRange(year, month)
  return apiRequest<Envelope<CalendarEvent>>(
    `/api/calendar/events?from=${encodeURIComponent(range.from)}&to=${encodeURIComponent(range.to)}`,
  )
}

async function getAnnotations(from: string, to: string): Promise<Envelope<DayAnnotation>> {
  return apiRequest<Envelope<DayAnnotation>>(
    `/api/calendar/annotations?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
  )
}

async function fetchSession(): Promise<SessionLite> {
  return apiRequest<SessionLite>('/api/me')
}

/** Cursor pages are bounded and stop only at the server's explicit end marker. */
async function fetchTaskPages(
  status: 'all' | 'open',
  range?: { from: string; to: string },
): Promise<CalendarTask[]> {
  const items: CalendarTask[] = []
  let cursor: string | null = null
  do {
    const params = new URLSearchParams({ status, limit: '100' })
    if (range) {
      params.set('from', range.from)
      params.set('to', range.to)
      params.set('bucket', 'dated')
    }
    if (cursor) params.set('cursor', cursor)
    const page = await apiRequest<Envelope<CalendarTask> & { next_cursor?: string | null }>(
      `/api/tasks?${params.toString()}`,
    )
    items.push(...page.items)
    cursor = page.next_cursor ?? null
  } while (cursor)
  return items
}

type OpenTaskPage = { items: CalendarTask[]; next_cursor?: string | null }

async function fetchOpenTaskPage(cursor: string | null = null): Promise<OpenTaskPage> {
  const params = new URLSearchParams({ status: 'open', bucket: 'open_picker', limit: '50' })
  if (cursor) params.set('cursor', cursor)
  return apiRequest<OpenTaskPage>(`/api/tasks?${params.toString()}`)
}

function useIsDesktop(): boolean {
  const [isDesktop, setIsDesktop] = useState(
    () => typeof window.matchMedia === 'function' && window.matchMedia('(min-width: 640px)').matches,
  )
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const query = window.matchMedia('(min-width: 640px)')
    const onChange = () => setIsDesktop(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])
  return isDesktop
}

export function CalendarScrollView() {
  const today = todayInVietnam()
  const todayMonthKey = today.slice(0, 7)
  const isDesktop = useIsDesktop()
  const containerRef = useRef<HTMLDivElement>(null)
  const [months, setMonths] = useState<YearMonth[]>(() =>
    monthsWindow(
      { year: Number(today.slice(0, 4)), month: Number(today.slice(5, 7)) },
      6,
    ),
  )
  const [visibleWeekKeys, setVisibleWeekKeys] = useState<string[]>([])
  const [selectedDay, setSelectedDay] = useState<string | null>(null)
  const visibleRef = useRef(new Map<string, boolean>())
  const extendingRef = useRef(false)
  const prependScrollRef = useRef<number | null>(null)

  const weekRows = useMemo(
    () =>
      months.flatMap(({ year, month }) =>
        monthWeeks(year, month).map((week) => ({ ...week, year, month })),
      ),
    [months],
  )

  const sessionQuery = useQuery({ ...sessionQuerySpec, queryFn: fetchSession })
  const sourcesQuery = useQuery({ ...sourcesQuerySpec, queryFn: getSources })
  const monthEventQueries = useQueries({
    queries: months.map(({ year, month }) => ({
      ...monthEventsQuerySpec(year, month),
      queryFn: () => getMonthEvents(year, month),
    })),
  })
  const annotationRange = useMemo(() => {
    const first = months[0]
    const last = months[months.length - 1]
    return {
      from: `${monthKey(first.year, first.month)}-01`,
      to: lastDayOfMonth(last.year, last.month),
    }
  }, [months])
  const taskRange = useMemo(() => {
    const first = months[0]
    const last = months[months.length - 1]
    return {
      from: monthFetchRange(first.year, first.month).from,
      to: monthFetchRange(last.year, last.month).to,
    }
  }, [months])
  const annotationsQuery = useQuery({
    ...annotationsQuerySpec(annotationRange.from, annotationRange.to),
    queryFn: () => getAnnotations(annotationRange.from, annotationRange.to),
  })
  const allTasksQuery = useQuery({
    ...calendarTasksQuerySpec('all', taskRange),
    queryFn: () => fetchTaskPages('all', taskRange),
  })

  const allEvents = useMemo(
    () => dedupeById(monthEventQueries.flatMap((query) => query.data?.items ?? [])),
    [monthEventQueries],
  )
  const eventsByDayMap = useMemo(() => eventsByDay(allEvents), [allEvents])
  const annotationsByDayMap = useMemo(
    () => annotationsByDay(annotationsQuery.data?.items ?? []),
    [annotationsQuery.data],
  )
  const tasksByDayMap = useMemo(
    () => tasksByDueDay(allTasksQuery.data ?? []),
    [allTasksQuery.data],
  )
  const sourceById = useMemo(
    () => new Map((sourcesQuery.data?.items ?? []).map((source) => [source.id, source])),
    [sourcesQuery.data],
  )
  const weekDaysByKey = useMemo(
    () => new Map(weekRows.map((row) => [row.key, row.days])),
    [weekRows],
  )

  const headerMonth = useMemo(() => {
    const visible = new Set(visibleWeekKeys)
    const first = weekRows.find((row) => visible.has(row.key))
    if (first) return { year: first.year, month: first.month }
    return { year: Number(today.slice(0, 4)), month: Number(today.slice(5, 7)) }
  }, [visibleWeekKeys, weekRows, today])

  const visibleDays = useMemo(
    () => visibleDayKeys(visibleWeekKeys, weekDaysByKey),
    [visibleWeekKeys, weekDaysByKey],
  )

  const privateLocked =
    !sessionQuery.data || remainingSeconds(sessionQuery.data.private_until) === 0
  const staleWithData =
    monthEventQueries.some((query) => query.isError && (query.data?.items.length ?? 0) > 0) ||
    (annotationsQuery.isError && (annotationsQuery.data?.items.length ?? 0) > 0) ||
    (allTasksQuery.isError && (allTasksQuery.data?.length ?? 0) > 0)
  const tasksTruncated = false

  /* IntersectionObserver on every week row, root = the scroll container. The
     callback only reports entries that CHANGED, so state is kept in a Map and
     derived as a value list (spec §5.2). No setTimeout throttle: the joined
     string comparison already drops no-op renders. */
  useEffect(() => {
    const container = containerRef.current
    if (!container || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(
      (entries) => {
        let changed = false
        for (const entry of entries) {
          const key = (entry.target as HTMLElement).dataset.weekKey
          if (!key) continue
          if (visibleRef.current.get(key) !== entry.isIntersecting) changed = true
          visibleRef.current.set(key, entry.isIntersecting)
        }
        if (!changed) return
        const next = [...visibleRef.current]
          .filter(([, value]) => value)
          .map(([key]) => key)
        setVisibleWeekKeys((previous) =>
          previous.join(',') === next.join(',') ? previous : next,
        )
      },
      { root: container, threshold: 0, rootMargin: `-${HEADER_HEIGHT}px 0px 0px 0px` },
    )
    for (const row of container.querySelectorAll<HTMLElement>('[data-week-key]')) {
      observer.observe(row)
    }
    return () => observer.disconnect()
  }, [weekRows])

  function scrollToRow(row: HTMLElement) {
    const container = containerRef.current
    if (!container) return
    const centered =
      row.offsetTop - (container.clientHeight - row.clientHeight) / 2 - HEADER_HEIGHT / 2
    container.scrollTop = Math.max(0, centered)
  }

  function findRowElement(predicate: (row: (typeof weekRows)[number]) => boolean): HTMLElement | null {
    const row = weekRows.find(predicate)
    if (!row) return null
    return (
      containerRef.current?.querySelector<HTMLElement>(`[data-week-key="${row.key}"]`) ?? null
    )
  }

  function scrollToMonth(target: YearMonth) {
    const el = findRowElement(
      (row) => monthKey(row.year, row.month) === monthKey(target.year, target.month),
    )
    if (el) scrollToRow(el)
  }

  function scrollToDay(day: string) {
    const target = monthKey(Number(day.slice(0, 4)), Number(day.slice(5, 7)))
    const el = findRowElement(
      (row) => monthKey(row.year, row.month) === target && row.days.includes(day),
    )
    if (el) scrollToRow(el)
  }

  function scrollToToday() {
    const el = findRowElement(
      (row) => monthKey(row.year, row.month) === todayMonthKey && row.days.includes(today),
    )
    if (el) scrollToRow(el)
  }

  /* Nhảy tới hôm nay trước lần vẽ đầu tiên: useLayoutEffect, không useEffect,
     để người dùng không thấy cảnh "mở giữa trang rồi giật lên" (spec §5.2). */
  useLayoutEffect(() => {
    scrollToToday()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function extendMonths(direction: 'prev' | 'next') {
    const container = containerRef.current
    if (!container || extendingRef.current) return
    extendingRef.current = true
    if (direction === 'prev') prependScrollRef.current = container.scrollHeight
    setMonths((current) => {
      if (direction === 'next') {
        const last = current[current.length - 1]
        return [
          ...current,
          ...Array.from({ length: EXTEND_MONTHS }, (_, index) =>
            addMonths(last.year, last.month, index + 1),
          ),
        ]
      }
      const first = current[0]
      return [
        ...Array.from({ length: EXTEND_MONTHS }, (_, index) =>
          addMonths(first.year, first.month, index - EXTEND_MONTHS),
        ),
        ...current,
      ]
    })
  }

  useLayoutEffect(() => {
    const container = containerRef.current
    if (prependScrollRef.current !== null && container) {
      const added = container.scrollHeight - prependScrollRef.current
      container.scrollTop += Math.max(0, added)
      prependScrollRef.current = null
    }
    extendingRef.current = false
  }, [months])

  function handleScroll() {
    const container = containerRef.current
    if (!container) return
    if (container.scrollTop < EDGE_EXTEND_PX) {
      extendMonths('prev')
    } else if (
      container.scrollTop + container.clientHeight >
      container.scrollHeight - EDGE_EXTEND_PX
    ) {
      extendMonths('next')
    }
  }

  return (
    <div className="-mx-5 flex gap-4 sm:mx-0">
      <div
        data-testid="calendar-scroll-container"
        ref={containerRef}
        onScroll={handleScroll}
        className="relative h-[calc(100dvh-13rem)] min-h-80 min-w-0 flex-1 overflow-y-auto rounded-xl border bg-card shadow-1"
      >
        <div className="sticky top-0 z-10 flex items-center justify-between gap-2 border-b bg-background px-3 py-2">
          <h3 data-testid="calendar-month-header" className="text-base font-extrabold">
            {monthLabel(headerMonth.year, headerMonth.month)}
          </h3>
          <Button
            data-testid="calendar-today-button"
            size="sm"
            variant="outline"
            onClick={scrollToToday}
          >
            Hôm nay
          </Button>
        </div>

        {staleWithData ? (
          <p
            data-testid="calendar-stale-indicator"
            className="border-b bg-warn-bg px-3 py-2 text-sm font-semibold text-warn"
          >
            Có thể chưa mới nhất — kiểm tra kết nối.
          </p>
        ) : null}
        {annotationsQuery.isError ? (
          <p
            data-testid="calendar-annotations-error"
            role="alert"
            className="border-b px-3 py-2 text-sm text-bad"
          >
            Không tải được dấu ngày.
          </p>
        ) : null}
        {allTasksQuery.isError ? (
          <p
            data-testid="calendar-tasks-error"
            role="alert"
            className="border-b px-3 py-2 text-sm text-bad"
          >
            Không tải được task.
          </p>
        ) : null}
        {tasksTruncated ? (
          <p
            data-testid="calendar-tasks-truncated"
            className="border-b px-3 py-2 text-sm text-muted-foreground"
          >
            Danh sách task dài hơn mức lịch hiển thị được — mở tab Task để xem đủ.
          </p>
        ) : null}

        {months.map(({ year, month }, index) => {
          const query = monthEventQueries[index]
          return (
            <div key={monthKey(year, month)} data-month-key={monthKey(year, month)} className="pt-3">
              <h4 className="mb-1 px-1 text-base font-extrabold">{monthLabel(year, month)}</h4>
              {query.isError ? (
                <p
                  data-testid="calendar-month-error"
                  role="alert"
                  className="px-1 pb-1 text-sm text-bad"
                >
                  Không tải được buổi của tháng này.
                </p>
              ) : null}
              <div className="grid grid-cols-7 gap-0.5 px-1 pb-1 text-center">
                {WEEKDAY_LABELS.map((label) => (
                  <span key={label} className="text-xs font-bold text-muted-foreground">
                    {label}
                  </span>
                ))}
              </div>
              {monthWeeks(year, month).map((week) => (
                <div key={week.key} data-week-key={week.key} className="grid grid-cols-7 gap-0.5">
                  {week.days.map((day) => (
                    <DayCell
                      key={day}
                      day={day}
                      isToday={day === today}
                      isOtherMonth={day.slice(0, 7) !== monthKey(year, month)}
                      events={eventsByDayMap.get(day) ?? []}
                      tasks={tasksByDayMap.get(day) ?? []}
                      annotations={annotationsByDayMap.get(day) ?? []}
                      chipLimit={isDesktop ? CHIP_LIMIT_DESKTOP : CHIP_LIMIT_MOBILE}
                      showAnnotationLabels={isDesktop}
                      sourceColorOf={(sourceId) => sourceById.get(sourceId)?.color ?? null}
                      onSelect={setSelectedDay}
                    />
                  ))}
                </div>
              ))}
            </div>
          )
        })}
      </div>

      <MiniNav
        anchor={headerMonth}
        visibleDays={visibleDays}
        onSelectDay={scrollToDay}
        onPrev={() => scrollToMonth(addMonths(headerMonth.year, headerMonth.month, -1))}
        onNext={() => scrollToMonth(addMonths(headerMonth.year, headerMonth.month, 1))}
      />

      <DayDetailDialog
        open={selectedDay !== null}
        onOpenChange={(next) => {
          if (!next) setSelectedDay(null)
        }}
        day={selectedDay ?? today}
        events={selectedDay ? (eventsByDayMap.get(selectedDay) ?? []) : []}
        tasks={selectedDay ? (tasksByDayMap.get(selectedDay) ?? []) : []}
        loadOpenTasks={fetchOpenTaskPage}
        annotations={selectedDay ? (annotationsByDayMap.get(selectedDay) ?? []) : []}
        sourceById={sourceById}
        privateLocked={privateLocked}
      />
    </div>
  )
}
