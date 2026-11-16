import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '@/api'
import { useOutbox } from '@/outbox/view'
import type { BootstrapSession } from '@/outbox/types'
import { TITLE_SUGGESTIONS_KEY, type TitleHistory } from '@/task-title-suggestions'

export function useTaskTitleSuggestions(disabled: boolean) {
  const client = useQueryClient()
  const outbox = useOutbox()
  const [used, setUsed] = useState(false)
  const session = client.getQueryData<BootstrapSession>(['session'])
  const enabled = used && !disabled && outbox.context.verified && !outbox.authRequired
  const query = useQuery({
    queryKey: [...TITLE_SUGGESTIONS_KEY, outbox.context.principal, session?.signed_in_at],
    queryFn: async ({ signal }): Promise<TitleHistory[]> => {
      const source = await apiRequest<unknown>('/api/tasks/title-suggestions', { signal, cache: 'no-store' })
      if (!Array.isArray(source)) return []
      return source.slice(0, 512).flatMap(row => {
        if (!row || typeof row !== 'object' || typeof row.title !== 'string' ||
          !Number.isInteger(row.count) || row.count < 1 || row.count > 512) return []
        return [{ title: row.title, count: row.count }]
      })
    },
    enabled,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: false,
  })
  useEffect(() => {
    const clear = () => {
      setUsed(false)
      void client.cancelQueries({ queryKey: TITLE_SUGGESTIONS_KEY })
      client.removeQueries({ queryKey: TITLE_SUGGESTIONS_KEY })
    }
    window.addEventListener('microsched:auth-lost', clear)
    window.addEventListener('microsched:visibility', clear)
    return () => {
      window.removeEventListener('microsched:auth-lost', clear)
      window.removeEventListener('microsched:visibility', clear)
    }
  }, [client])
  // While Task mutations revalidate, the old snapshot can contain a title that
  // was just removed or moved to Private. Do not offer it as a draft candidate.
  return { history: enabled && !query.isStale ? query.data ?? [] : [], activate: () => setUsed(true) }
}
