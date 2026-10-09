import type { QueryClient } from '@tanstack/react-query'
import type { MimiChangeSet, MimiConversation } from './mimi-api'
export type MimiDecisionIntent = { conversationId: string; changeSet: MimiChangeSet; choice: 'confirm' | 'reject'; key: string }
export function hasAuthoritativeMimiRefusal(intent: MimiDecisionIntent, changes: MimiChangeSet[]): boolean {
  return changes.some((change) => change.id === intent.changeSet.id && change.digest === intent.changeSet.digest && change.nonce === intent.changeSet.nonce && ['invalidated', 'expired', 'superseded', 'rejected', 'stale'].includes(change.state))
}
// Publish the matching server refusal before releasing UNKNOWN's intent lock.
// Cancel older inflight reads so they cannot restore cached eligible metadata.
export async function publishAuthoritativeMimiRefusal(client: QueryClient, intent: MimiDecisionIntent, snapshot: MimiConversation): Promise<boolean> {
  if (snapshot.id !== intent.conversationId || !hasAuthoritativeMimiRefusal(intent, snapshot.change_sets)) return false
  const key = ['mimi', 'conversation', intent.conversationId]
  await client.cancelQueries({ queryKey: key, exact: true })
  await client.cancelQueries({ queryKey: ['mimi', 'current'], exact: true })
  client.setQueryData(key, snapshot)
  client.setQueryData<MimiConversation | null>(['mimi', 'current'], (current) => current?.id === intent.conversationId ? snapshot : current)
  return true
}
const prefix = 'mimi-decision-intent:'
// Only opaque write bindings, never conversation prose or device credentials.
export function saveMimiIntent(intent: MimiDecisionIntent) {
  const { id, digest, nonce } = intent.changeSet
  sessionStorage.setItem(prefix + intent.conversationId, JSON.stringify({ conversationId: intent.conversationId, id, digest, nonce, choice: intent.choice, key: intent.key }))
}
export function readMimiIntent(conversationId: string, changes: MimiChangeSet[]): MimiDecisionIntent | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(prefix + conversationId) ?? 'null')
    if (!value || value.conversationId !== conversationId || !['confirm', 'reject'].includes(value.choice) || typeof value.key !== 'string') return null
    const changeSet = changes.find((c) => c.id === value.id && c.digest === value.digest && c.nonce === value.nonce)
    return changeSet ? { conversationId, changeSet, choice: value.choice, key: value.key } : null
  } catch { return null }
}
export function clearMimiIntent(conversationId: string) { sessionStorage.removeItem(prefix + conversationId) }
