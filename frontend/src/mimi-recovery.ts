import type { MimiChangeSet } from './mimi-api'
export type MimiDecisionIntent = { conversationId: string; changeSet: MimiChangeSet; choice: 'confirm' | 'reject'; key: string }
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
