import type { MimiChangeSet, MimiConversation } from './mimi-api'

export type MimiPreviewBinding = { conversationId: string; id: string; digest: string; nonce: string }

export function activeMimiPreview(changes: MimiChangeSet[]): MimiChangeSet | undefined {
  const pending = changes.filter(item => item.state === 'pending')
  // Multiple active previews violate the one-active contract. Never guess from
  // array ordering which frozen payload the Owner meant to confirm.
  return pending.length === 1 ? pending[0] : undefined
}

export function matchesMimiPreview(conversation: MimiConversation, change: MimiChangeSet | undefined, binding: MimiPreviewBinding): boolean {
  return conversation.id === binding.conversationId && change?.state === 'pending'
    && change.id === binding.id && change.digest === binding.digest && change.nonce === binding.nonce
}

export function blockedNewMimiPreview(conversation: MimiConversation): boolean {
  return conversation.runs.at(-1)?.error_code === 'pending_preview_requires_decision'
}
