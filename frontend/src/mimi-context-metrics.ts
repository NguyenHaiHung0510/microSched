import type { MimiContextComposition, MimiProviderCall, MimiConversation } from '@/mimi-api'

export const CONTEXT_BUCKETS = [
  ['policy', 'System policy and output instructions'],
  ['authority', 'Current authority and provenance metadata'],
  ['schemas', 'Native tool and response schemas'],
  ['checkpoint', 'Semantic checkpoint and active constraints'],
  ['transcript', 'Retained transcript suffix'],
  ['task_evidence', 'Initial task evidence'],
  ['current_pending_loop', 'Current turn and pending/current-loop state'],
  ['framing', 'Framing and other input overhead'],
] as const

export function lastMeasuredMain(calls: MimiProviderCall[]): MimiProviderCall | undefined {
  return calls.filter(c => (c.purpose ?? 'main') === 'main' && c.paid_dispatch !== false && c.state === 'succeeded'
    && Boolean(c.requested_model) && c.actual_model === c.requested_model && Boolean(c.actual_provider)
    && Number.isSafeInteger(c.usage.prompt_tokens) && c.usage.prompt_tokens >= 0).at(-1)
}

export function validContextComposition(value?: MimiContextComposition | null): boolean {
  return value?.state === 'measured_bytes' && value.method === 'serialized_utf8_bytes' && value.unit === 'bytes'
    && value.for === 'assembled_request_not_next_unsent_request' && Number.isSafeInteger(value.total)
    && value.total! >= 0 && value.categories?.length === CONTEXT_BUCKETS.length
    && new Set(value.categories.map(x => x.id)).size === CONTEXT_BUCKETS.length
    && value.categories.every(x => CONTEXT_BUCKETS.some(([id]) => id === x.id) && x.state === 'measured_bytes'
      && Number.isSafeInteger(x.value) && x.value >= 0)
    && value.categories.reduce((sum, x) => sum + x.value, 0) === value.total
}


export function lastMeasuredInput(conversation: MimiConversation): number | null {
  if (conversation.metrics) return conversation.metrics.last_measured_input?.tokens ?? null
  return lastMeasuredMain(conversation.provider_calls ?? [])?.usage.prompt_tokens ?? null
}

export const formatMetric = (value: number | null | undefined) => value == null ? '—' : value.toLocaleString('vi-VN')
