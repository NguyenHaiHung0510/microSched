/**
 * Query keys and options for every 010b calendar-grid query, kept in one
 * module so the polling guardrail is testable at the boundary (spec §2.8):
 * the app-wide QueryClient in main.tsx polls every visible query each second,
 * so each 010b query MUST opt out explicitly with `refetchInterval: false`.
 * Removing the flag here fails `calendar-queries.test.ts`, not a manual QA.
 */

export const CALENDAR_FAMILY_KEY = ['calendar'] as const

export const CALENDAR_QUERY_OPTIONS = Object.freeze({
  refetchInterval: false,
} as const)

export type CalendarQuerySpec = {
  queryKey: readonly unknown[]
  refetchInterval: false
}

export const sourcesQuerySpec: CalendarQuerySpec = {
  queryKey: ['calendar', 'sources'],
  refetchInterval: false,
}

export const monthEventsQuerySpec = (year: number, month: number): CalendarQuerySpec => ({
  queryKey: ['calendar', 'events', year, month],
  refetchInterval: false,
})

export const annotationsQuerySpec = (from: string, to: string): CalendarQuerySpec => ({
  queryKey: ['calendar', 'annotations', from, to],
  refetchInterval: false,
})

export const calendarTasksQuerySpec = (status: 'all' | 'open'): CalendarQuerySpec => ({
  queryKey: ['calendar', 'tasks', status],
  refetchInterval: false,
})

export const sessionQuerySpec: CalendarQuerySpec = {
  queryKey: ['session'],
  refetchInterval: false,
}

/** Every spec the grid can mount, for the polling regression test. */
export const CALENDAR_QUERY_SPECS: CalendarQuerySpec[] = [
  sourcesQuerySpec,
  monthEventsQuerySpec(2026, 8),
  annotationsQuerySpec('2026-08-01', '2026-08-31'),
  calendarTasksQuerySpec('all'),
  calendarTasksQuerySpec('open'),
  sessionQuerySpec,
]
