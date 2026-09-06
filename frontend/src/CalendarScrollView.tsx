import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueries, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, GripVertical, Plus } from 'lucide-react'
import { toast } from 'sonner'

import { apiRequest } from '@/api'
import {
  formatVietnamTime,
  VIETNAM_TIME_ZONE,
  sourceColorToken,
  todayInVietnam,
  type CalendarEvent,
  type CalendarSource,
} from '@/calendar-ui'
import {
  CHIP_LIMIT_DESKTOP,
  CHIP_LIMIT_MOBILE,
  WEEKDAY_LABELS,
  addMonths,
  annotationsByDay,
  dedupeById,
  eventsByDay,
  formatFullVietnameseDate,
  formatShortVietnamDate,
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
  CALENDAR_FAMILY_KEY,
  annotationsQuerySpec,
  calendarTasksQuerySpec,
  monthEventsQuerySpec,
  sessionQuerySpec,
  sourcesQuerySpec,
} from '@/calendar-queries'
import { DayCell, type DropTaskPayload } from '@/DayCell'
import { DayDetailDialog } from '@/DayDetailDialog'
import { MiniNav } from '@/MiniNav'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { remainingSeconds } from '@/private-gate'

type Envelope<T> = { items: T[] }
type SessionLite = { private_until: string | null }

const HEADER_HEIGHT = 56
const EDGE_EXTEND_PX = 80
const EXTEND_MONTHS = 6
const CALENDAR_MODE_KEY = 'microsched:calendar-mode'

function getSavedCalendarMode(): 'grid' | 'agenda' {
  try {
    const saved = localStorage.getItem(CALENDAR_MODE_KEY)
    if (saved === 'agenda' || saved === 'grid') return saved
  } catch {
    // Ignore storage errors
  }
  return 'grid'
}

function saveCalendarMode(mode: 'grid' | 'agenda') {
  try {
    localStorage.setItem(CALENDAR_MODE_KEY, mode)
  } catch {
    // Ignore storage errors
  }
}

function ensureMonthIncluded(target: YearMonth, currentMonths: YearMonth[]): YearMonth[] {
  if (currentMonths.length === 0) return [target]
  const targetIndex = target.year * 12 + (target.month - 1)
  const firstIndex = currentMonths[0].year * 12 + (currentMonths[0].month - 1)
  const lastIndex =
    currentMonths[currentMonths.length - 1].year * 12 +
    (currentMonths[currentMonths.length - 1].month - 1)

  if (targetIndex >= firstIndex && targetIndex <= lastIndex) {
    return currentMonths
  }
  if (targetIndex < firstIndex) {
    const prepended: YearMonth[] = []
    for (let i = targetIndex; i < firstIndex; i++) {
      prepended.push({ year: Math.floor(i / 12), month: (i % 12) + 1 })
    }
    return [...prepended, ...currentMonths]
  }
  const appended: YearMonth[] = []
  for (let i = lastIndex + 1; i <= targetIndex; i++) {
    appended.push({ year: Math.floor(i / 12), month: (i % 12) + 1 })
  }
  return [...currentMonths, ...appended]
}

function formatTaskDue(dueAt: string): string {
  try {
    return new Intl.DateTimeFormat('vi-VN', {
      timeZone: VIETNAM_TIME_ZONE,
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(dueAt))
  } catch {
    return dueAt
  }
}

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
  const queryClient = useQueryClient()
  const today = todayInVietnam()
  const todayMonthKey = today.slice(0, 7)
  const isDesktop = useIsDesktop()
  const containerRef = useRef<HTMLDivElement>(null)
  const [quickTitle, setQuickTitle] = useState('')
  const [calendarMode, setCalendarMode] = useState<'grid' | 'agenda'>(getSavedCalendarMode)
  const [showMiniNav, setShowMiniNav] = useState(true)
  const [agendaDay, setAgendaDay] = useState(today)
  const [agendaMonth, setAgendaMonth] = useState<YearMonth>(() => ({
    year: Number(today.slice(0, 4)),
    month: Number(today.slice(5, 7)),
  }))
  const [agendaQuickTitle, setAgendaQuickTitle] = useState('')
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
  const gridScrollTopRef = useRef<number | null>(null)
  const hasInitializedRef = useRef(false)
  const agendaInputRef = useRef<HTMLInputElement>(null)

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

  const refreshCalendar = () =>
    void queryClient.invalidateQueries({ queryKey: CALENDAR_FAMILY_KEY })
  const refreshAll = () => {
    void queryClient.invalidateQueries({ queryKey: ['tasks'] })
    refreshCalendar()
  }

  const createQuickTask = useMutation({
    mutationFn: (variables: { title: string; due_on: string }) =>
      apiRequest<CalendarTask>('/api/tasks', {
        method: 'POST',
        body: JSON.stringify({
          title: variables.title,
          status: 'open',
          priority: null,
          due_precision: 'date',
          due_on: variables.due_on,
          due_at: null,
          is_private: false,
        }),
      }),
    onSuccess: (_data, variables) => {
      setQuickTitle('')
      refreshAll()
      toast.success(`Đã thêm task vào ${formatShortVietnamDate(variables.due_on)}`)
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Không thể tạo task.')
    },
  })

  const toggleTaskStatus = useMutation({
    mutationFn: (variables: { taskId: string; status: 'open' | 'completed' }) =>
      apiRequest<CalendarTask>(`/api/tasks/${variables.taskId}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: variables.status }),
      }),
    onSuccess: () => {
      refreshAll()
    },
  })

  const rescheduleTask = useMutation({
    mutationFn: (variables: {
      taskId: string
      due_on: string
      previousDueOn?: string
    }) =>
      apiRequest<CalendarTask>(`/api/tasks/${variables.taskId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          due_precision: 'date',
          due_on: variables.due_on,
          due_at: null,
        }),
      }),
    onSuccess: (_data, variables) => {
      refreshAll()
      toast(`Đã dời task sang ${formatShortVietnamDate(variables.due_on)}`, {
        action: variables.previousDueOn
          ? {
              label: 'Hoàn tác',
              onClick: () =>
                rescheduleTask.mutate({
                  taskId: variables.taskId,
                  due_on: variables.previousDueOn!,
                }),
            }
          : undefined,
      })
    },
  })

  function handleDropTask(day: string, payload: DropTaskPayload) {
    if (payload.kind === 'quick-new-task') {
      createQuickTask.mutate({ title: payload.title, due_on: day })
    } else if (payload.kind === 'reschedule-task') {
      rescheduleTask.mutate({
        taskId: payload.taskId,
        due_on: day,
        previousDueOn: payload.fromDay,
      })
    }
  }

  function handleQuickSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = quickTitle.trim()
    if (!trimmed) return
    createQuickTask.mutate({ title: trimmed, due_on: today })
  }

  const createAgendaTask = useMutation({
    mutationFn: (variables: { title: string; due_on: string }) =>
      apiRequest<CalendarTask>('/api/tasks', {
        method: 'POST',
        body: JSON.stringify({
          title: variables.title,
          status: 'open',
          priority: null,
          due_precision: 'date',
          due_on: variables.due_on,
          due_at: null,
          is_private: false,
        }),
      }),
    onSuccess: (_data, variables) => {
      setAgendaQuickTitle('')
      refreshAll()
      toast.success(`Đã thêm task vào ${formatShortVietnamDate(variables.due_on)}`)
      agendaInputRef.current?.focus()
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Không thể tạo task.')
      agendaInputRef.current?.focus()
    },
  })

  function handleAgendaQuickSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = agendaQuickTitle.trim()
    if (!trimmed || createAgendaTask.isPending) return
    createAgendaTask.mutate({ title: trimmed, due_on: agendaDay })
  }

  function handleModeChange(mode: 'grid' | 'agenda') {
    if (mode === calendarMode) return
    if (mode === 'agenda') {
      if (containerRef.current) {
        gridScrollTopRef.current = containerRef.current.scrollTop
      }
      if (!agendaDay) setAgendaDay(today)
    }
    setCalendarMode(mode)
    saveCalendarMode(mode)
  }

  function handleTodayClick() {
    const targetMonth = {
      year: Number(today.slice(0, 4)),
      month: Number(today.slice(5, 7)),
    }
    setAgendaMonth(targetMonth)
    setAgendaDay(today)
    setMonths((prev) => ensureMonthIncluded(targetMonth, prev))
    if (calendarMode === 'grid') {
      scrollToToday()
    }
  }

  function navigateAgendaMonth(delta: number) {
    const nextMonth = addMonths(agendaMonth.year, agendaMonth.month, delta)
    setAgendaMonth(nextMonth)
    const isCurrent = monthKey(nextMonth.year, nextMonth.month) === todayMonthKey
    setAgendaDay(isCurrent ? today : `${monthKey(nextMonth.year, nextMonth.month)}-01`)
    setMonths((prev) => ensureMonthIncluded(nextMonth, prev))
  }

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

  const agendaMonthIndex = months.findIndex(
    (m) => m.year === agendaMonth.year && m.month === agendaMonth.month,
  )
  const agendaMonthEventQuery =
    agendaMonthIndex >= 0 ? monthEventQueries[agendaMonthIndex] : undefined
  const agendaDayEvents = eventsByDayMap.get(agendaDay) ?? []
  const agendaDayTasks = tasksByDayMap.get(agendaDay) ?? []
  const agendaDayAnnotations = annotationsByDayMap.get(agendaDay) ?? []

  const staleWithData =
    monthEventQueries.some((query) => query.isError && (query.data?.items.length ?? 0) > 0) ||
    (annotationsQuery.isError && (annotationsQuery.data?.items.length ?? 0) > 0) ||
    (allTasksQuery.isError && (allTasksQuery.data?.length ?? 0) > 0)
  const tasksTruncated = false

  useEffect(() => {
    if (calendarMode !== 'grid') return
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
  }, [weekRows, calendarMode])

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

  useLayoutEffect(() => {
    if (calendarMode !== 'grid') return
    const container = containerRef.current
    if (!container) return
    if (!hasInitializedRef.current) {
      scrollToToday()
      hasInitializedRef.current = true
    } else if (gridScrollTopRef.current !== null) {
      container.scrollTop = gridScrollTopRef.current
    } else {
      scrollToToday()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [calendarMode])

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
    if (calendarMode !== 'grid') return
    const container = containerRef.current
    if (!container) return
    gridScrollTopRef.current = container.scrollTop
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
       <div
         className={cn(
           'sticky top-0 z-10 border-b bg-background px-3 py-2',
           'flex flex-col gap-2',
         )}
       >
         <div className="flex flex-wrap items-center justify-between gap-2 w-full">
           <h3 data-testid="calendar-month-header" className="text-base font-extrabold truncate">
             {calendarMode === 'agenda'
               ? monthLabel(agendaMonth.year, agendaMonth.month)
               : monthLabel(headerMonth.year, headerMonth.month)}
           </h3>
            <div className="flex flex-wrap items-center gap-1.5">
              <div
                className="flex items-center gap-1 rounded-lg bg-muted p-1"
                role="group"
                aria-label="Chế độ xem tháng"
              >
                <Button
                  data-testid="calendar-mode-toggle-grid"
                  size="default"
                  variant={calendarMode === 'grid' ? 'secondary' : 'ghost'}
                  aria-pressed={calendarMode === 'grid'}
                  className="min-h-11 h-11 px-3 text-xs sm:text-sm font-semibold"
                  onClick={() => handleModeChange('grid')}
                >
                  Lưới
                </Button>
                <Button
                  data-testid="calendar-mode-toggle-agenda"
                  size="default"
                  variant={calendarMode === 'agenda' ? 'secondary' : 'ghost'}
                  aria-pressed={calendarMode === 'agenda'}
                  className="min-h-11 h-11 px-3 text-xs sm:text-sm font-semibold"
                  onClick={() => handleModeChange('agenda')}
                >
                  Theo ngày
                </Button>
              </div>
              {calendarMode === 'grid' ? (
                <Button
                  data-testid="calendar-toggle-sidebar"
                  size="default"
                  variant="outline"
                  className="hidden sm:inline-flex min-h-11 h-11 px-3 text-xs font-semibold"
                  onClick={() => setShowMiniNav((s) => !s)}
                >
                  {showMiniNav ? 'Thu gọn lịch nhỏ' : 'Hiện lịch nhỏ'}
                </Button>
              ) : null}
              <Button
                data-testid="calendar-today-button"
                size="default"
                variant="outline"
                className="min-h-11 h-11 px-3 text-xs sm:text-sm font-semibold"
                onClick={handleTodayClick}
              >
                Hôm nay
              </Button>
            </div>
          </div>

          {/* Tooltip & Quick Task Entry bar for desktop */}
          {isDesktop && calendarMode === 'grid' ? (
            <form
              onSubmit={handleQuickSubmit}
              data-testid="calendar-quick-task-bar"
              className="flex items-center gap-2"
            >
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div className="min-w-0 flex-1">
                      <Input
                        data-testid="calendar-quick-task-input"
                        placeholder="Nhập task nhanh… kéo chip hoặc Enter để lưu vào Hôm nay"
                        value={quickTitle}
                        onChange={(e) => setQuickTitle(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                  </TooltipTrigger>
                  <TooltipContent>
                    Nhập task rồi kéo chip sang ô ngày bất kỳ trên lịch để xếp lịch, hoặc bấm Thêm để đặt cho Hôm nay.
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>

              {quickTitle.trim() ? (
                <div
                  data-testid="calendar-quick-task-draggable"
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData(
                      'application/json',
                      JSON.stringify({
                        kind: 'quick-new-task',
                        title: quickTitle.trim(),
                      }),
                    )
                    e.dataTransfer.effectAllowed = 'copy'
                  }}
                  className="flex cursor-grab items-center gap-1 rounded-md border border-dashed border-primary bg-accent px-2 py-1 text-xs font-bold text-accent-foreground active:cursor-grabbing"
                >
                  <GripVertical className="size-3.5" />
                  <span className="max-w-28 truncate">{quickTitle.trim()}</span>
                </div>
              ) : null}

              <Button
                type="submit"
                size="sm"
                variant="secondary"
                disabled={!quickTitle.trim() || createQuickTask.isPending}
                data-testid="calendar-quick-task-submit"
                className="h-8 px-2.5 text-xs font-semibold"
              >
                <Plus data-icon="inline-start" className="size-3.5" />
               Thêm
             </Button>
           </form>
         ) : null}

          {/* Sticky Weekday Labels Grid (T2–CN) */}
          {calendarMode === 'grid' ? (
            <div className="grid grid-cols-7 gap-0.5 px-0.5 pt-1 text-center">
              {WEEKDAY_LABELS.map((label) => (
                <span key={label} className="text-xs font-bold text-muted-foreground">
                  {label}
                </span>
              ))}
            </div>
          ) : null}
       </div>

       {staleWithData ? (
          <p
            data-testid="calendar-stale-indicator"
            className="border-b bg-warn-bg px-3 py-2 text-sm font-semibold text-warn"
          >
            Có thể chưa mới nhất — kiểm tra kết nối.
          </p>
        ) : null}
        {calendarMode === 'grid' && annotationsQuery.isError ? (
          <p
            data-testid="calendar-annotations-error"
            role="alert"
            className="border-b px-3 py-2 text-sm text-bad"
          >
            Không tải được dấu ngày.
          </p>
        ) : null}
        {calendarMode === 'grid' && allTasksQuery.isError ? (
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

        {calendarMode === 'agenda' ? (
          <div data-testid="calendar-agenda-container" className="space-y-4 p-3 sm:p-4">
            {/* Compact Month Picker */}
            <div
              data-testid="calendar-agenda-picker"
              className="rounded-xl border bg-card p-3 shadow-sm space-y-2"
            >
              <div className="flex items-center justify-between gap-2 pb-2 border-b">
                <Button
                  data-testid="calendar-agenda-prev-month"
                  variant="ghost"
                  aria-label="Tháng trước"
                  className="min-h-11 min-w-11 size-11 p-0 flex items-center justify-center"
                  onClick={() => navigateAgendaMonth(-1)}
                >
                  <ChevronLeft className="size-5" />
                </Button>
                <span
                  data-testid="calendar-agenda-month-title"
                  className="text-sm font-extrabold text-foreground"
                >
                  {monthLabel(agendaMonth.year, agendaMonth.month)}
                </span>
                <Button
                  data-testid="calendar-agenda-next-month"
                  variant="ghost"
                  aria-label="Tháng sau"
                  className="min-h-11 min-w-11 size-11 p-0 flex items-center justify-center"
                  onClick={() => navigateAgendaMonth(1)}
                >
                  <ChevronRight className="size-5" />
                </Button>
              </div>

              <div className="grid grid-cols-7 gap-1 text-center">
                {WEEKDAY_LABELS.map((label) => (
                  <span key={label} className="text-xs font-bold text-muted-foreground">
                    {label}
                  </span>
                ))}
                {monthWeeks(agendaMonth.year, agendaMonth.month).flatMap((week) =>
                  week.days.map((day) => {
                    const inCurrentMonth =
                      day.slice(0, 7) === monthKey(agendaMonth.year, agendaMonth.month)
                    if (!inCurrentMonth) {
                      return <div key={day} aria-hidden="true" className="min-h-9 h-10 w-full" />
                    }
                    const isDayToday = day === today
                    const isSelected = day === agendaDay
                    const dayEvents = eventsByDayMap.get(day) ?? []
                    const dayTasks = tasksByDayMap.get(day) ?? []
                    const dayAnnotations = annotationsByDayMap.get(day) ?? []
                    const dayNum = Number(day.slice(8, 10))

                    return (
                      <Button
                        key={day}
                        data-testid="calendar-agenda-day-button"
                        data-day={day}
                        data-selected={isSelected ? 'true' : undefined}
                        variant={isSelected ? 'secondary' : 'ghost'}
                        aria-label={day}
                        aria-pressed={isSelected}
                        onClick={() => setAgendaDay(day)}
                        className={cn(
                          'flex min-h-9 min-w-9 h-10 w-full min-w-0 flex-col items-center justify-center rounded-lg p-0 text-xs transition-colors',
                          isSelected && 'bg-primary text-primary-foreground font-bold hover:bg-primary/90 hover:text-primary-foreground',
                          !isSelected && isDayToday && 'border border-primary font-bold text-primary',
                        )}
                      >
                        <span className="text-xs font-semibold">{dayNum}</span>
                        <div className="flex items-center gap-0.5 mt-0.5">
                          {dayEvents.length > 0 ? (
                            <span
                              aria-hidden="true"
                              className={cn(
                                'size-1 rounded-full',
                                isSelected ? 'bg-primary-foreground' : 'bg-primary',
                              )}
                            />
                          ) : null}
                          {dayTasks.length > 0 ? (
                            <span
                              aria-hidden="true"
                              className={cn(
                                'size-1 rounded-full',
                                isSelected ? 'bg-primary-foreground/70' : 'bg-muted-foreground',
                              )}
                            />
                          ) : null}
                          {dayAnnotations.length > 0 ? (
                            <span
                              aria-hidden="true"
                              className={cn(
                                'size-1 rounded-full',
                                isSelected ? 'bg-primary-foreground/90' : 'bg-warn',
                              )}
                            />
                          ) : null}
                        </div>
                      </Button>
                    )
                  }),
                )}
              </div>
            </div>

            {/* Selected Day Agenda Content */}
            <div
              data-testid="calendar-agenda-view"
              className="rounded-xl border bg-card p-4 shadow-1 space-y-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-3">
                <div className="flex items-center gap-2">
                  <h4
                    data-testid="calendar-agenda-day-title"
                    className="text-base font-extrabold text-foreground"
                  >
                    {formatFullVietnameseDate(agendaDay)}
                  </h4>
                  {agendaDay === today ? (
                    <Badge variant="secondary" className="bg-primary/10 text-primary text-xs font-bold">
                      Hôm nay
                    </Badge>
                  ) : null}
                </div>
                <Button
                  data-testid="calendar-agenda-open-detail"
                  size="default"
                  variant="outline"
                  className="min-h-11 h-11 px-3 text-xs sm:text-sm font-semibold"
                  onClick={() => setSelectedDay(agendaDay)}
                >
                  Chi tiết / Sửa
                </Button>
              </div>

              {/* Quick Add for this day */}
              <form
                onSubmit={handleAgendaQuickSubmit}
                data-testid="calendar-agenda-quick-task-bar"
                className="flex gap-2"
              >
                <Input
                  ref={agendaInputRef}
                  data-testid="calendar-agenda-quick-task-input"
                  placeholder="Thêm task cho ngày này…"
                  value={agendaQuickTitle}
                  disabled={createAgendaTask.isPending}
                  onChange={(e) => setAgendaQuickTitle(e.target.value)}
                  className="min-h-11 h-11 text-sm flex-1"
                />
                <Button
                  data-testid="calendar-agenda-quick-task-submit"
                  type="submit"
                  size="default"
                  disabled={!agendaQuickTitle.trim() || createAgendaTask.isPending}
                  className="min-h-11 h-11 px-4 text-sm font-semibold shrink-0"
                >
                  <Plus data-icon="inline-start" />
                  Thêm
                </Button>
              </form>

              {/* Annotations */}
              {annotationsQuery.isLoading ? (
                <p
                  data-testid="calendar-agenda-annotations-loading"
                  className="text-xs text-muted-foreground"
                >
                  Đang tải dấu ngày…
                </p>
              ) : annotationsQuery.isError ? (
                <div
                  data-testid="calendar-agenda-annotations-error"
                  role="alert"
                  className="flex items-center justify-between gap-2 rounded-lg border border-destructive/20 bg-destructive/10 p-2 text-xs text-destructive"
                >
                  <span>Không tải được dấu ngày.</span>
                  <Button
                    size="sm"
                    variant="outline"
                    className="min-h-6 h-6 px-2 text-xs font-semibold"
                    onClick={() => void annotationsQuery.refetch()}
                  >
                    Thử lại
                  </Button>
                </div>
              ) : agendaDayAnnotations.length > 0 ? (
                <div className="space-y-1.5">
                  <h5 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Dấu ngày
                  </h5>
                  {agendaDayAnnotations.map((ann) => (
                    <div
                      key={ann.id}
                      className="flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-semibold"
                    >
                      <span
                        aria-hidden="true"
                        className="size-2.5 rounded-full shrink-0"
                        style={{ backgroundColor: sourceColorToken(ann.color) }}
                      />
                      <span className="font-bold">{ann.label}</span>
                      {ann.note_md ? (
                        <span className="text-muted-foreground truncate">· {ann.note_md}</span>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : null}

              {/* Events section */}
              <div data-testid="calendar-agenda-events" className="space-y-2">
                <div className="flex items-center justify-between">
                  <h5 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Buổi ({agendaMonthEventQuery?.isLoading ? '…' : agendaDayEvents.length})
                  </h5>
                </div>
                {agendaMonthEventQuery?.isLoading ? (
                  <p
                    data-testid="calendar-agenda-events-loading"
                    className="text-sm text-muted-foreground"
                  >
                    Đang tải buổi…
                  </p>
                ) : agendaMonthEventQuery?.isError ? (
                  <div
                    data-testid="calendar-agenda-events-error"
                    role="alert"
                    className="flex items-center justify-between gap-2 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive"
                  >
                    <span>Không tải được buổi của tháng này.</span>
                    <Button
                      size="sm"
                      variant="outline"
                      className="min-h-8 h-8 px-2.5 text-xs font-semibold"
                      onClick={() => void agendaMonthEventQuery.refetch()}
                    >
                      Thử lại
                    </Button>
                  </div>
                ) : agendaDayEvents.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Không có buổi nào trong ngày.</p>
                ) : (
                  agendaDayEvents.map((event) => {
                    const source = sourceById.get(event.source_id)
                    return (
                      <div
                        key={event.id}
                        data-testid="calendar-agenda-event-card"
                        data-event-id={event.id}
                        className="rounded-lg border bg-background p-3 shadow-sm space-y-1 transition-colors"
                      >
                        <div className="flex items-start gap-2.5">
                          <span
                            aria-hidden="true"
                            className="mt-1 size-3 shrink-0 rounded-full"
                            style={{
                              backgroundColor: sourceColorToken(source?.color ?? null),
                            }}
                          />
                          <div className="min-w-0 flex-1 space-y-0.5">
                            <p
                              data-testid="calendar-agenda-event-title"
                              className="text-base font-bold text-foreground break-words min-w-0"
                            >
                              {event.title}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {formatVietnamTime(event)} · {source?.name ?? 'Nguồn'}
                            </p>
                            {event.location ? (
                              <p className="text-xs text-foreground/80 break-words min-w-0">
                                📍 {event.location}
                              </p>
                            ) : null}
                            {event.description_md ? (
                              <p className="text-xs text-muted-foreground whitespace-pre-wrap break-words min-w-0 pt-1">
                                {event.description_md}
                              </p>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    )
                  })
                )}
              </div>

              {/* Tasks section */}
              <div data-testid="calendar-agenda-tasks" className="space-y-2">
                <div className="flex items-center justify-between">
                  <h5 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Task đến hạn ({allTasksQuery.isLoading ? '…' : agendaDayTasks.length})
                  </h5>
                </div>
                {allTasksQuery.isLoading ? (
                  <p
                    data-testid="calendar-agenda-tasks-loading"
                    className="text-sm text-muted-foreground"
                  >
                    Đang tải task…
                  </p>
                ) : allTasksQuery.isError ? (
                  <div
                    data-testid="calendar-agenda-tasks-error"
                    role="alert"
                    className="flex items-center justify-between gap-2 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive"
                  >
                    <span>Không tải được task.</span>
                    <Button
                      size="sm"
                      variant="outline"
                      className="min-h-8 h-8 px-2.5 text-xs font-semibold"
                      onClick={() => void allTasksQuery.refetch()}
                    >
                      Thử lại
                    </Button>
                  </div>
                ) : agendaDayTasks.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Không có task đến hạn hôm nay.</p>
                ) : (
                  agendaDayTasks.map((task) => (
                    <div
                      key={task.id}
                      data-testid="calendar-agenda-task-card"
                      data-task-id={task.id}
                      className="flex items-center gap-3 rounded-lg border bg-background p-3 shadow-sm transition-colors"
                    >
                      <Checkbox
                        data-testid="calendar-agenda-task-toggle"
                        checked={task.status === 'completed'}
                        onCheckedChange={(checked) =>
                          toggleTaskStatus.mutate({
                            taskId: task.id,
                            status: checked === true ? 'completed' : 'open',
                          })
                        }
                        className="size-4 rounded-sm"
                        aria-label={`Đổi trạng thái ${task.title}`}
                      />
                      <span
                        data-testid="calendar-agenda-task-title"
                        className={cn(
                          'min-w-0 flex-1 text-sm font-semibold break-words',
                          task.status === 'completed' && 'line-through text-muted-foreground',
                        )}
                      >
                        {task.title}
                      </span>
                      {task.due_at ? (
                        <span className="text-xs text-muted-foreground shrink-0">
                          {formatTaskDue(task.due_at)}
                        </span>
                      ) : null}
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        ) : (
          months.map(({ year, month }, index) => {
          const query = monthEventQueries[index]
          const currentMonthKey = monthKey(year, month)
          return (
            <div key={currentMonthKey} data-month-key={currentMonthKey} className="pt-3">
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
                  {week.days.map((day) => {
                    const isSameMonth = day.slice(0, 7) === currentMonthKey
                    if (!isSameMonth) {
                      return (
                        <div
                          key={day}
                          aria-hidden="true"
                          className="h-auto min-h-16 w-full rounded-lg border border-transparent p-1 pointer-events-none opacity-0 sm:min-h-24 md:min-h-28"
                        />
                      )
                    }
                    return (
                      <DayCell
                        key={day}
                        day={day}
                        isToday={day === today}
                        isOtherMonth={false}
                        isDesktop={isDesktop}
                      events={eventsByDayMap.get(day) ?? []}
                      tasks={tasksByDayMap.get(day) ?? []}
                      annotations={annotationsByDayMap.get(day) ?? []}
                      chipLimit={isDesktop ? CHIP_LIMIT_DESKTOP : CHIP_LIMIT_MOBILE}
                      showAnnotationLabels={isDesktop}
                      sourceColorOf={(sourceId) => sourceById.get(sourceId)?.color ?? null}
                        onSelect={setSelectedDay}
                        onToggleTask={(taskId, status) =>
                          toggleTaskStatus.mutate({ taskId, status })
                        }
                        onDropTask={handleDropTask}
                      />
                    )
                  })}
                </div>
              ))}
            </div>
          )
        }))}
      </div>

      {showMiniNav && calendarMode === 'grid' ? (
        <MiniNav
          anchor={headerMonth}
          visibleDays={visibleDays}
          onSelectDay={scrollToDay}
          onPrev={() => scrollToMonth(addMonths(headerMonth.year, headerMonth.month, -1))}
          onNext={() => scrollToMonth(addMonths(headerMonth.year, headerMonth.month, 1))}
        />
      ) : null}

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
