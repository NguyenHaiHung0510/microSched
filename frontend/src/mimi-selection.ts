import { useSyncExternalStore } from 'react'
import type { QueryClient } from '@tanstack/react-query'
import type { MimiConversationPage, MimiConversationSummary } from '@/mimi-api'

const key = 'mimi.standard.selected-conversation.v1'
const changed = 'mimi-conversation-selected'
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
let fallback: string | null = null
const drafts = new Map<string, string>()
const draftChanged = 'mimi-composer-changed'

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
  if (id === null) {
    drafts.clear()
    window.dispatchEvent(new Event(draftChanged))
  }
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
  for (const state of ['active', 'all']) {
    client.setQueryData<MimiConversationPage>(['mimi', 'conversations', state], (old) => ({
      items: [created, ...(old?.items ?? []).filter((item) => item.id !== created.id)],
      next_cursor: old?.next_cursor ?? null,
    }))
  }
  selectMimiConversation(created.id)
}

export function readMimiComposerDraft(id: string): string {
  return drafts.get(id) ?? ''
}

export function setMimiComposerDraft(id: string, text: string): void {
  if (text) drafts.set(id, text.slice(0, 12_000))
  else drafts.delete(id)
  window.dispatchEvent(new Event(draftChanged))
}

export function useMimiComposerDraft(id: string | undefined): [string, (text: string) => void] {
  // Unsent prose stays ephemeral in this tab, never sessionStorage or a request.
  const text = useSyncExternalStore(
    (notify) => {
      window.addEventListener(draftChanged, notify)
      return () => window.removeEventListener(draftChanged, notify)
    },
    () => id ? readMimiComposerDraft(id) : '',
    () => '',
  )
  return [text, (next) => { if (id) setMimiComposerDraft(id, next) }]
}
