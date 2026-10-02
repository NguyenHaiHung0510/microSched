import { useSyncExternalStore } from 'react'
import type { QueryClient } from '@tanstack/react-query'
import type { MimiConversationPage, MimiConversationSummary } from '@/mimi-api'

const key = 'mimi.standard.selected-conversation.v1'
const changed = 'mimi-conversation-selected'
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
let fallback: string | null = null

// Only an opaque conversation ID is kept in this tab. API ownership and the
// fetched accessible list still determine what can actually be displayed.
export function readMimiSelection(): string | null {
  try {
    const value = window.sessionStorage.getItem(key)
    return value && uuid.test(value) ? value : null
  } catch {
    return fallback
  }
}

export function selectMimiConversation(id: string | null): void {
  fallback = id && uuid.test(id) ? id : null
  try {
    if (fallback) window.sessionStorage.setItem(key, fallback)
    else window.sessionStorage.removeItem(key)
  } catch { /* A storage restriction must not break the current conversation. */ }
  window.dispatchEvent(new Event(changed))
}

function subscribe(callback: () => void): () => void {
  window.addEventListener(changed, callback)
  return () => window.removeEventListener(changed, callback)
}

export function useMimiSelection(): [string | null, typeof selectMimiConversation] {
  const id = useSyncExternalStore(subscribe, readMimiSelection, () => null)
  return [id, selectMimiConversation]
}

export function selectCreatedMimiConversation(client: QueryClient, created: MimiConversationSummary): void {
  client.setQueryData<MimiConversationPage>(['mimi', 'conversations', 'active'], (old) => ({
    items: [created, ...(old?.items ?? []).filter((item) => item.id !== created.id)],
    next_cursor: old?.next_cursor ?? null,
  }))
  selectMimiConversation(created.id)
}
