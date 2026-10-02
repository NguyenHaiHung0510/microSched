import { useInfiniteQuery } from '@tanstack/react-query'
import { fetchMimiConversations, type MimiConversationPage } from '@/mimi-api'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'

export function mergeMimiConversationPages(pages: MimiConversationPage[]) {
  const seen = new Set<string>()
  return pages.flatMap((page) => page.items).filter((item) => {
    if (seen.has(item.id)) return false
    seen.add(item.id)
    return true
  })
}

export function useMimiConversationList(state: 'active' | 'archived' | 'all') {
  const query = useInfiniteQuery({
    queryKey: ['mimi', 'conversations', 'paged', state],
    queryFn: ({ pageParam }) => fetchMimiConversations(state, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    ...NO_POLLING_QUERY_OPTIONS,
  })
  return { ...query, items: mergeMimiConversationPages(query.data?.pages ?? []) }
}
