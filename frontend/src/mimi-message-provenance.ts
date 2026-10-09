import type { MimiMessage } from '@/mimi-api'

const SERVER_PRODUCERS = new Set([
  'context_budget_stop', 'checkpoint_unknown', 'checkpoint_materialization_failed',
  'provider_output_rejected', 'provider_terminal', 'local_deterministic_result',
  'conversation_frontier_changed', 'preview_frontier_changed',
  'pending_preview_requires_decision', 'preview_prepared', 'operation_committed',
  'process_loss_recovery', 'collection_committed', 'undo_prepared',
])

/** Explicit owner-bound API evidence only. Legacy/unknown stays unclassified. */
export function isVerifiedServerNotice(message: MimiMessage): boolean {
  const proof = message.provenance
  return message.role === 'assistant' && typeof message.run_id === 'string'
    && proof?.source === 'server_verified' && proof.origin === 'server_notice'
    && proof.version === 1 && typeof proof.producer_code === 'string'
    && SERVER_PRODUCERS.has(proof.producer_code)
    && Number.isSafeInteger(proof.event_sequence) && Number(proof.event_sequence) > 0
}
