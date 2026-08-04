/**
 * Pure calendar-grid logic for the 010b scroll view.
 *
 * Every date boundary here is a Vietnam calendar day (+07:00), never the device
 * timezone: an event at 23:30+07:00 must land on the day the owner sees it.
 * Weeks start on Monday, matching the old app and Vietnamese convention.
 */

import {
  addVietnamDays,
  VIETNAM_TIME_ZONE,
  type CalendarEvent,
} from '@/calendar-ui'

export type YearMonth = { year: number; month: number }

export type WeekRow = {
  key: string
  days: string[]
}

export type DayAnnotation = {
  id: string
  starts_on: string
  ends_on: string
  label: string
  note_md: string | null
  color: string | null
  is_private: boolean
  created_at: string | null
  updated_at: string | null
}

/** Full task shape returned by GET /api/tasks, kept beside the slim chip type. */
export type CalendarTask = {
  id: string
  title: string
  body_md: string | null
  status: 'open' | 'completed'
  priority: 'p1' | 'p2' | 'p3' | null
  due_at: string | null
  is_private: boolean
  pinned: boolean
  created_at: string | null
  updated_at: string | null
  items: Array<{
    id: string
    content: string
    is_completed: boolean
    position: number
  }>
}

export type TaskSummary = {
  id: string
  title: string
  status: 'open' | 'completed'
  due_at: string | null
  created_at: string | null
}

export type DayChip =
  | { kind: 'event'; event: CalendarEvent }
  | { kind: 'task'; task: TaskSummary }

export const WEEKDAY_LABELS = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN']

export const CHIP_LIMIT_MOBILE = 2
export const CHIP_LIMIT_DESKTOP = 3

export function pad2(value: number): string {
  return String(value).padStart(2, '0')
}

export function monthKey(year: number, month: number): string {
  return `${year}-${pad2(month)}`
}

export function parseMonthKey(key: string): YearMonth {
  const [year, month] = key.split('-').map(Number)
  return { year, month }
}

function vnDateParts(value: Date): Record<string, string> {
  return Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', {
      timeZone: VIETNAM_TIME_ZONE,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
      .formatToParts(value)
      .filter(({ type }) => type !== 'literal')
      .map(({ type, value: part }) => [type, part]),
  )
}

export function vnDayKey(value: string | Date): string {
  const date = typeof value === 'string' ? new Date(value) : value
  const parts = vnDateParts(date)
  return `${parts.year}-${parts.month}-${parts.day}`
}

/** Monday of the week containing a Vietnam calendar day. */
export function mondayOfWeek(day: string): string {
  const date = new Date(`${day}T00:00:00Z`)
  const daysSinceMonday = (date.getUTCDay() + 6) % 7
  date.setUTCDate(date.getUTCDate() - daysSinceMonday)
  return date.toISOString().slice(0, 10)
}

export function addMonths(year: number, month: number, delta: number): YearMonth {
  const index = year * 12 + (month - 1) + delta
  return { year: Math.floor(index / 12), month: (index % 12) + 1 }
}

export function lastDayOfMonth(year: number, month: number): string {
  return addVietnamDays(`${year}-${pad2(month)}-01`, new Date(Date.UTC(year, month, 0)).getUTCDate() - 1)
}

/**
 * Weeks of a month as Monday-first rows, keyed by (year, month, week index)
 * instead of by first day: two adjacent month blocks render the same calendar
 * week twice, and the key must distinguish those duplicate DOM rows.
 */
export function monthWeeks(year: number, month: number): WeekRow[] {
  const firstDay = `${year}-${pad2(month)}-01`
  const lastDay = addVietnamDays(firstDay, new Date(Date.UTC(year, month, 0)).getUTCDate() - 1)
  const weeks: WeekRow[] = []
  let cursor = mondayOfWeek(firstDay)

  while (cursor <= lastDay) {
    const days: string[] = []
    for (let offset = 0; offset < 7; offset += 1) {
      days.push(addVietnamDays(cursor, offset))
    }
    weeks.push({ key: `${monthKey(year, month)}-w${weeks.length}`, days })
    cursor = addVietnamDays(cursor, 7)
  }
  return weeks
}

/** Half-open month window: [first day 00:00+07:00, first day of next month). */
export function monthFetchRange(year: number, month: number): { from: string; to: string } {
  const next = addMonths(year, month, 1)
  return {
    from: `${year}-${pad2(month)}-01T00:00:00+07:00`,
    to: `${next.year}-${pad2(next.month)}-01T00:00:00+07:00`,
  }
}

export function monthsWindow(center: YearMonth, radius: number): YearMonth[] {
  const result: YearMonth[] = []
  for (let delta = -radius; delta <= radius; delta += 1) {
    result.push(addMonths(center.year, center.month, delta))
  }
  return result
}

export function monthLabel(year: number, month: number): string {
  return new Intl.DateTimeFormat('vi-VN', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, month - 1, 1)))
}

export function formatShortVietnamDate(day: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: VIETNAM_TIME_ZONE,
    day: '2-digit',
    month: '2-digit',
  }).format(new Date(`${day}T12:00:00+07:00`))
}

export function formatFullVietnameseDate(day: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: VIETNAM_TIME_ZONE,
    weekday: 'long',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(`${day}T12:00:00+07:00`))
}

export function endOfDayVietnam(day: string): string {
  return `${day}T23:59:00+07:00`
}

export function dedupeById<T extends { id: string }>(items: T[]): T[] {
  const seen = new Set<string>()
  const result: T[] = []
  for (const item of items) {
    if (seen.has(item.id)) continue
    seen.add(item.id)
    result.push(item)
  }
  return result
}

/**
 * Light tint + dark text for source-colored chips and annotation bars. Only
 * existing tokens from index.css are used; the key set is SOURCE_COLORS.
 */
export function sourceTone(color: string | null): { background: string; color: string } {
  switch (color) {
    case 'rose':
      return { background: 'var(--rose-100)', color: 'var(--rose-700)' }
    case 'amber':
      return { background: 'var(--warn-bg)', color: 'var(--warn)' }
    case 'emerald':
      return { background: 'var(--ok-bg)', color: 'var(--ok)' }
    case 'sky':
      // The sky key maps to --primary (rose-700) in SOURCE_COLORS, so it shares
      // the warm rose ramp instead of inventing a blue token.
      return { background: 'var(--rose-100)', color: 'var(--rose-700)' }
    case 'violet':
      return { background: 'var(--rose-200)', color: 'var(--rose-800)' }
    default:
      return { background: 'var(--n-100)', color: 'var(--n-700)' }
  }
}

export function isTaskOverdue(dueAt: string | null, now: number): boolean {
  return dueAt !== null && Date.parse(dueAt) < now
}

/**
 * The "Dời một việc sang ngày này" chooser: open tasks first, overdue before
 * the rest, then due_at, then created_at (spec §5.6 mục 1).
 */
export function sortOpenTasksForMove<T extends TaskSummary>(
  tasks: T[],
  now: number,
): T[] {
  return [...tasks]
    .filter((task) => task.status === 'open')
    .sort((left, right) => {
      const leftOverdue = isTaskOverdue(left.due_at, now) ? 0 : 1
      const rightOverdue = isTaskOverdue(right.due_at, now) ? 0 : 1
      if (leftOverdue !== rightOverdue) return leftOverdue - rightOverdue
      return (
        Date.parse(left.due_at ?? '') - Date.parse(right.due_at ?? '') ||
        (left.created_at ?? left.id).localeCompare(right.created_at ?? right.id)
      )
    })
}

/** Every Vietnam calendar day a time-range annotation covers, inclusive. */
export function annotationDays(annotation: DayAnnotation): string[] {
  const days: string[] = []
  let cursor = annotation.starts_on
  while (cursor <= annotation.ends_on) {
    days.push(cursor)
    cursor = addVietnamDays(cursor, 1)
  }
  return days
}

function sortedEvents(events: CalendarEvent[]): CalendarEvent[] {
  return [...events].sort((left, right) =>
    Date.parse(left.starts_at) - Date.parse(right.starts_at) ||
    left.id.localeCompare(right.id),
  )
}

/**
 * Group events by the Vietnam day they occupy. An event crossing midnight
 * belongs to both calendar days it touches.
 */
export function eventsByDay(events: CalendarEvent[]): Map<string, CalendarEvent[]> {
  const groups = new Map<string, CalendarEvent[]>()
  for (const event of dedupeById(events)) {
    const startDay = vnDayKey(event.starts_at)
    const endDay = vnDayKey(event.ends_at)
    for (const day of new Set([startDay, endDay])) {
      const current = groups.get(day) ?? []
      current.push(event)
      groups.set(day, current)
    }
  }
  for (const [day, dayEvents] of groups) {
    groups.set(day, sortedEvents(dayEvents))
  }
  return groups
}

export function annotationsByDay(
  annotations: DayAnnotation[],
): Map<string, DayAnnotation[]> {
  const groups = new Map<string, DayAnnotation[]>()
  for (const annotation of dedupeById(annotations)) {
    for (const day of annotationDays(annotation)) {
      const current = groups.get(day) ?? []
      current.push(annotation)
      groups.set(day, current)
    }
  }
  for (const [day, dayAnnotations] of groups) {
    groups.set(
      day,
      [...dayAnnotations].sort((left, right) =>
        (left.created_at ?? left.id).localeCompare(right.created_at ?? right.id),
      ),
    )
  }
  return groups
}

export function tasksByDueDay<T extends TaskSummary>(tasks: T[]): Map<string, T[]> {
  const groups = new Map<string, T[]>()
  for (const task of dedupeById(tasks)) {
    if (!task.due_at) continue
    const day = vnDayKey(task.due_at)
    const current = groups.get(day) ?? []
    current.push(task)
    groups.set(day, current)
  }
  for (const [day, dayTasks] of groups) {
    groups.set(
      day,
      [...dayTasks].sort((left, right) =>
        Date.parse(left.due_at ?? '') - Date.parse(right.due_at ?? '') ||
        (left.created_at ?? left.id).localeCompare(right.created_at ?? right.id),
      ),
    )
  }
  return groups
}

export type MergedChips = { chips: DayChip[]; overflow: number }

/**
 * One merged, truncated list: events first (by start time), then tasks (by due
 * time); everything beyond the limit collapses into a single +N count.
 */
export function mergeDayChips(
  events: CalendarEvent[],
  tasks: TaskSummary[],
  limit: number,
): MergedChips {
  const chips: DayChip[] = [
    ...sortedEvents(events).map((event) => ({ kind: 'event' as const, event })),
    ...tasks.map((task) => ({ kind: 'task' as const, task })),
  ]
  return {
    chips: chips.slice(0, limit),
    overflow: Math.max(0, chips.length - limit),
  }
}

/** Week keys of every day a set of visible weeks covers, for mini-nav shading. */
export function visibleDayKeys(weekKeys: string[], weekDaysByKey: Map<string, string[]>): Set<string> {
  const days = new Set<string>()
  for (const key of weekKeys) {
    for (const day of weekDaysByKey.get(key) ?? []) {
      days.add(day)
    }
  }
  return days
}
