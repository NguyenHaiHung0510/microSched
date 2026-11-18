import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { garden, gardenOptions } from './api'
import { localInput } from './presentation'

export const historyPoll = (query: { state: { status: string } }) => query.state.status === 'error' ? 60_000 : 15_000

export function useGardenTimeline(active: boolean) {
  const [filters, setFilters] = useState(() => {
    const today = localInput(new Date().toISOString()).slice(0, 10)
    return { from_day: today, to_day: today, source: 'all', result: 'all' }
  })
  const [cursors, setCursors] = useState<string[]>([])
  const params = new URLSearchParams({ view: 'sessions' })
  for (const [key, value] of Object.entries(filters)) if (value && value !== 'all') params.set(key, value)
  if (cursors.length) params.set('cursor', cursors[cursors.length - 1])
  const badRange = !!(filters.from_day && filters.to_day && filters.from_day > filters.to_day)
  const query = useQuery({
    queryKey: ['migarden', 'history', params.toString()],
    queryFn: ({ signal }) => garden.timeline(params, signal),
    ...gardenOptions, enabled: active && !badRange, refetchInterval: historyPoll,
  })
  return {
    filters, query, badRange,
    update(key: keyof typeof filters, value: string) {
      setFilters(old => ({ ...old, [key]: value })); setCursors([])
    },
    allDates() { setFilters(old => ({ ...old, from_day: '', to_day: '' })); setCursors([]) },
    newer: cursors.length > 0 ? () => setCursors(old => old.slice(0, -1)) : undefined,
    older: query.data?.next_cursor ? () => setCursors(old => [...old, query.data!.next_cursor!]) : undefined,
  }
}

export type GardenTimelineModel = ReturnType<typeof useGardenTimeline>
