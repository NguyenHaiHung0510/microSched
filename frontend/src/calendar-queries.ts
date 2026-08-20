/**
 * Query keys and options for every 010b calendar-grid query, kept in one
 * module so the polling guardrail is testable at the boundary (spec §2.8).
 * Polling is now opt-in app-wide, but Calendar keeps an explicit no-poll
 * contract because its dynamic month queries fan out as the scroll expands.
 */

import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'

export const CALENDAR_FAMILY_KEY = ['calendar'] as const

export const CALENDAR_QUERY_OPTIONS = NO_POLLING_QUERY_OPTIONS

export type CalendarQuerySpec = {
  queryKey: readonly unknown[]
  refetchInterval: false
}

export const sourcesQuerySpec: CalendarQuerySpec = {
  queryKey: ['calendar', 'sources'],
  ...CALENDAR_QUERY_OPTIONS,
}

export const monthEventsQuerySpec = (year: number, month: number): CalendarQuerySpec => ({
  queryKey: ['calendar', 'events', year, month],
  ...CALENDAR_QUERY_OPTIONS,
})

export const annotationsQuerySpec = (from: string, to: string): CalendarQuerySpec => ({
  queryKey: ['calendar', 'annotations', from, to],
  ...CALENDAR_QUERY_OPTIONS,
})

export const calendarTasksQuerySpec = (
  status: 'all' | 'open',
  range?: { from: string; to: string },
): CalendarQuerySpec => ({
  queryKey: ['calendar', 'tasks', status, range?.from ?? null, range?.to ?? null],
  ...CALENDAR_QUERY_OPTIONS,
})

export const sessionQuerySpec: CalendarQuerySpec = {
  queryKey: ['session'],
  ...CALENDAR_QUERY_OPTIONS,
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
