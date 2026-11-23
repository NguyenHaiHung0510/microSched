import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { garden, gardenOptions, gardenKey } from './api'
import { localInput } from './presentation'
import { humanActive } from '@/human-activity'

export const historyPoll = (query: { state: { status: string } }) => !humanActive() ? false : query.state.status === 'error' ? 60_000 : 15_000

export function defaultHistoryFilters(now = new Date()) {
  const today = localInput(now.toISOString()).slice(0, 10)
  const from = new Date(today + 'T00:00:00+07:00')
  from.setUTCDate(from.getUTCDate() - 6)
  return { from_day: localInput(from.toISOString()).slice(0, 10), to_day: today, source: 'all', result: 'all', category: 'all' }
}

export function useGardenTimeline(active: boolean) {
  const client = useQueryClient()
  const [filters, setFilters] = useState(defaultHistoryFilters)
  const [cursors, setCursors] = useState<string[]>([])
  const params = new URLSearchParams({ view: 'sessions' })
  for (const [key, value] of Object.entries(filters)) if (value && (value !== 'all' || key === 'category')) params.set(key, value)
  if (cursors.length) params.set('cursor', cursors[cursors.length - 1])
  const badRange = !!(filters.from_day && filters.to_day && filters.from_day > filters.to_day)
  const query = useQuery({
    queryKey: gardenKey('history', params.toString()),
    queryFn: async ({ signal }) => {
      const data = await garden.timeline(params, signal)
      signal.throwIfAborted()
      // Apply/reject evidence is not fully exposed by StateView. The selected
      // version joins the existing 15s timeline read; no new polling timer.
      if (humanActive()) void client.refetchQueries({
        queryKey: gardenKey('version'), type: 'active',
        predicate: query => query.state.fetchStatus === 'idle' && Date.now() - query.state.dataUpdatedAt >= 15_000,
      }, { cancelRefetch: false })
      return data
    },
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
