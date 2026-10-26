import type { MimiFeedback } from '@/mimi-api'
import { feedbackComment, feedbackFieldOverflow } from '@/mimi-owner-feedback'

export type SupplementDraft = {
  text: string
  expected?: string
  reasons: string[]
  revision: number
  intent: SupplementIntent | null
  savedRevision: number | null
}
export type SupplementIntent = {
  conversationId: string
  targetId: string
  clientId: string
  comment: string
  expected?: string
  revision: number
}
export const emptyDraft = (): SupplementDraft => ({ text: '', reasons: [], revision: 0, intent: null, savedRevision: null })
export const draftKey = (conversationId: string, targetId: string) => ['mimi-feedback-draft', 'positive-supplement', conversationId, targetId]

export function hasUnsentSupplement(draft: { text?: string; expected?: string; reasons?: unknown[]; intent?: unknown } | undefined) {
  return !!(draft?.text || draft?.expected || draft?.reasons?.length || draft?.intent)
}

/** A retry always sends the original body/key, even after a draft edit. */
export function supplementIntent(draft: SupplementDraft, conversationId: string, targetId: string, clientId: string): SupplementIntent | null {
  if (draft.intent) return draft.intent
  if (feedbackFieldOverflow(draft.text) || feedbackFieldOverflow(draft.expected ?? '')) return null
  if (!draft.text.trim() && !draft.reasons.length && !draft.expected?.trim()) return null
  return { conversationId, targetId, clientId, comment: feedbackComment('positive', draft.reasons, draft.text), expected: draft.expected ?? '', revision: draft.revision }
}
export function acknowledgeSupplement(draft: SupplementDraft, intent: SupplementIntent): SupplementDraft {
  if (draft.intent?.clientId !== intent.clientId) return draft
  return draft.revision === intent.revision
    ? { ...emptyDraft(), revision: draft.revision + 1, savedRevision: draft.revision + 1 }
    : { ...draft, intent: null }
}

export function verifySupplementAck(saved: MimiFeedback, intent: SupplementIntent): MimiFeedback {
  if (saved.client_id !== intent.clientId || saved.target_type !== 'turn' || saved.target_id !== intent.targetId) throw new Error('Feedback acknowledgment target mismatch')
  return saved
}
