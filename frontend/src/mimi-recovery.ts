import type { QueryClient } from '@tanstack/react-query'
import { validateMimiReceipt, type MimiChangeSet, type MimiConversation, type MimiReceipt } from './mimi-api'
import { isMimiSessionCurrent, mimiSessionEpoch } from './mimi-session-boundary'
export type MimiDecisionTarget = Pick<MimiChangeSet, 'id' | 'digest' | 'nonce'> & {
  operation?: { operation_id: string; tool?: MimiChangeSet['operation']['tool'] }
  run_id?: string
}
export type MimiDecisionIntent = { conversationId: string; changeSet: MimiDecisionTarget; choice: 'confirm' | 'reject'; key: string }
export type MimiDispatchIntent = MimiDecisionIntent & { changeSet: MimiChangeSet }
export type MimiDecisionFence = Pick<MimiDecisionTarget, 'id' | 'digest' | 'nonce'>
export const mimiDecisionFenceKey = (conversationId: string | null | undefined) => ['mimi-decision-fences', conversationId]
export const sameMimiDecisionBinding = (left: MimiDecisionTarget, right: MimiDecisionTarget) => left.id === right.id && left.digest === right.digest && left.nonce === right.nonce
function fence(client: QueryClient, intent: MimiDecisionIntent) {
  const { id, digest, nonce } = intent.changeSet
  client.setQueryData<MimiDecisionFence[]>(mimiDecisionFenceKey(intent.conversationId), old => [
    ...(old ?? []).filter(item => !sameMimiDecisionBinding(item, intent.changeSet)), { id, digest, nonce },
  ])
}

export async function publishMimiDecisionAck(client: QueryClient, intent: MimiDecisionIntent, saved: MimiReceipt | { change_set_id: string; state: 'rejected' }, epoch = mimiSessionEpoch(client)) {
  if (!isMimiSessionCurrent(client, epoch)) throw new Error('Mimi session changed')
  if (intent.choice === 'confirm') {
    if (!('executed_at' in saved)) throw new Error('Confirmation receipt missing')
    validateMimiReceipt(intent.changeSet, saved)
  } else if (!('state' in saved) || saved.state !== 'rejected' || saved.change_set_id !== intent.changeSet.id) throw new Error('Reject acknowledgment binding mismatch')
  fence(client, intent)
  await client.cancelQueries({ queryKey: ['mimi', 'conversation', intent.conversationId], exact: true })
  await client.cancelQueries({ queryKey: ['mimi', 'current'], exact: true })
  if (!isMimiSessionCurrent(client, epoch)) throw new Error('Mimi session changed')
  const publish = (snapshot: MimiConversation | null | undefined) => {
    if (!snapshot || snapshot.id !== intent.conversationId) return snapshot
    return { ...snapshot, change_sets: snapshot.change_sets.map(change => sameMimiDecisionBinding(change, intent.changeSet)
      ? { ...change, state: intent.choice === 'reject' ? 'rejected' : 'executed' } : change),
      receipts: 'executed_at' in saved && !snapshot.receipts.some(receipt => receipt.id === saved.id) ? [...snapshot.receipts, saved] : snapshot.receipts }
  }
  client.setQueryData(['mimi', 'conversation', intent.conversationId], publish)
  client.setQueryData(['mimi', 'current'], publish)
}
export function hasAuthoritativeMimiRefusal(intent: MimiDecisionIntent, changes: MimiChangeSet[]): boolean {
  return changes.some((change) => change.id === intent.changeSet.id && change.digest === intent.changeSet.digest && change.nonce === intent.changeSet.nonce && ['invalidated', 'expired', 'superseded', 'rejected', 'stale'].includes(change.state))
}
// Publish the matching server refusal before releasing UNKNOWN's intent lock.
// Cancel older inflight reads so they cannot restore cached eligible metadata.
export async function publishAuthoritativeMimiRefusal(client: QueryClient, intent: MimiDecisionIntent, snapshot: MimiConversation, epoch = mimiSessionEpoch(client)): Promise<boolean> {
  if (!isMimiSessionCurrent(client, epoch)) return false
  if (snapshot.id !== intent.conversationId || !hasAuthoritativeMimiRefusal(intent, snapshot.change_sets)) return false
  const key = ['mimi', 'conversation', intent.conversationId]
  await client.cancelQueries({ queryKey: key, exact: true })
  await client.cancelQueries({ queryKey: ['mimi', 'current'], exact: true })
  if (!isMimiSessionCurrent(client, epoch)) return false
  fence(client, intent)
  client.setQueryData(key, snapshot)
  client.setQueryData<MimiConversation | null>(['mimi', 'current'], (current) => current?.id === intent.conversationId ? snapshot : current)
  return true
}
const prefix = 'mimi-decision-intent:'
// Only opaque write bindings, never conversation prose or device credentials.
export function saveMimiIntent(intent: MimiDecisionIntent) {
  const { id, digest, nonce } = intent.changeSet
  sessionStorage.setItem(prefix + intent.conversationId, JSON.stringify({ conversationId: intent.conversationId, id, digest, nonce, choice: intent.choice, key: intent.key,
    operationId: intent.changeSet.operation?.operation_id, tool: intent.changeSet.operation?.tool, runId: intent.changeSet.run_id }))
}
export function readMimiIntent(conversationId: string, changes: MimiChangeSet[]): MimiDecisionIntent | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(prefix + conversationId) ?? 'null')
    if (!value || value.conversationId !== conversationId || !['confirm', 'reject'].includes(value.choice)
      || !['key', 'id', 'digest', 'nonce'].every(field => typeof value[field] === 'string' && value[field])) return null
    const changeSet = changes.find((c) => c.id === value.id && c.digest === value.digest && c.nonce === value.nonce
      && (typeof value.operationId !== 'string' || c.operation?.operation_id === value.operationId))
    const opaque: MimiDecisionTarget = { id: value.id, digest: value.digest, nonce: value.nonce,
      ...(typeof value.operationId === 'string' ? { operation: { operation_id: value.operationId,
        ...(['task.create.v1', 'task.collection.v1'].includes(value.tool) ? { tool: value.tool } : {}) } } : {}),
      ...(typeof value.runId === 'string' ? { run_id: value.runId } : {}) }
    return { conversationId, changeSet: changeSet ?? opaque, choice: value.choice, key: value.key }
  } catch { return null }
}
export function clearMimiIntent(conversationId: string) { sessionStorage.removeItem(prefix + conversationId) }
