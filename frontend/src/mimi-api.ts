import { apiRequest } from '@/api'

export type MimiMessage = {
  id: string
  run_id: string | null
  client_id: string | null
  sequence: number
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string
}

export type MimiRun = {
  id: string
  generation: number
  state: string
  provider_outcome: 'succeeded' | 'failed' | 'unknown' | null
  deadline: string
  error_code: string | null
  created_at: string
  completed_at: string | null
}

export type MimiChangeSet = {
  id: string
  run_id: string
  state: string
  digest: string
  nonce: string
  expires_at: string
  policy_version: string
  operation: {
    operation_id: string
    tool: 'task.create.v1'
    args: {
      id: string
      title: string
      body_md: string | null
      status: string
      priority: string | null
      due_precision: string
      due_on: string | null
      due_at: string | null
      is_private: false
      items: string[]
    }
  }
}

export type MimiReceipt = {
  id: string
  change_set_id: string
  operation_id: string
  task_id: string
  digest: string
  result: Record<string, unknown>
  executed_at: string
}

export type MimiFeedback = {
  id: string
  client_id: string
  target_type: string
  target_id: string
  state: string
  unresolved: boolean
  created_at: string
}

export type MimiEvent = {
  id: string
  run_id: string
  sequence: number
  kind: string
  payload: Record<string, unknown>
  created_at: string
}

export type MimiConversation = {
  id: string
  sensitivity: 'standard'
  generation: number
  messages: MimiMessage[]
  runs: MimiRun[]
  change_sets: MimiChangeSet[]
  receipts: MimiReceipt[]
  events: MimiEvent[]
  feedback: MimiFeedback[]
}

const MIMI_WRITE_HEADERS = { 'X-Mimi-CSRF': '1' }

export function fetchCurrentMimiConversation(): Promise<MimiConversation | null> {
  return apiRequest('/api/mimi/conversations/current')
}

export function createMimiConversation(): Promise<Pick<MimiConversation, 'id' | 'sensitivity' | 'generation'>> {
  return apiRequest('/api/mimi/conversations', {
    method: 'POST',
    headers: MIMI_WRITE_HEADERS,
    body: JSON.stringify({}),
  })
}

export function sendMimiMessage(
  conversationId: string,
  content: string,
  expectedGeneration: number,
  clientId: string,
): Promise<MimiConversation> {
  return apiRequest(`/api/mimi/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: MIMI_WRITE_HEADERS,
    body: JSON.stringify({
      client_id: clientId,
      content,
      expected_generation: expectedGeneration,
    }),
  })
}

export function decideMimiChangeSet(
  changeSet: MimiChangeSet,
  decision: 'confirm' | 'reject',
  idempotencyKey: string,
): Promise<MimiReceipt | { change_set_id: string; state: 'rejected' }> {
  return apiRequest(`/api/mimi/change-sets/${changeSet.id}/decision`, {
    method: 'POST',
    headers: { ...MIMI_WRITE_HEADERS, 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify({
      digest: changeSet.digest,
      nonce: changeSet.nonce,
      decision,
    }),
  })
}

export function saveMimiFeedback(
  conversationId: string,
  receiptId: string,
  comment: string,
  clientId: string,
): Promise<MimiFeedback> {
  return apiRequest(`/api/mimi/conversations/${conversationId}/feedback`, {
    method: 'POST',
    headers: MIMI_WRITE_HEADERS,
    body: JSON.stringify({
      client_id: clientId,
      target_type: 'receipt',
      target_id: receiptId,
      comment,
      evidence_bundle_ids: [],
    }),
  })
}
