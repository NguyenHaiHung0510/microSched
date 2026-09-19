import { ApiError, apiRequest } from '@/api'

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
  title?: string
  title_source?: 'auto' | 'owner'
  title_locked?: boolean
  generation: number
  metadata_version?: number
  archived_at?: string | null
  updated_at?: string
  messages: MimiMessage[]
  runs: MimiRun[]
  change_sets: MimiChangeSet[]
  receipts: MimiReceipt[]
  events: MimiEvent[]
  feedback: MimiFeedback[]
}

export type MimiConversationSummary = {
  id: string
  sensitivity: 'standard'
  title: string
  title_source: 'auto' | 'owner'
  title_locked: boolean
  generation: number
  metadata_version: number
  archived_at: string | null
  updated_at: string
  latest_run_state: string | null
}

export type MimiConversationPage = {
  items: MimiConversationSummary[]
  next_cursor: string | null
}

const MIMI_WRITE_HEADERS = { 'X-Mimi-CSRF': '1' }

export function fetchCurrentMimiConversation(): Promise<MimiConversation | null> {
  return apiRequest('/api/mimi/conversations/current')
}

export function fetchMimiConversation(conversationId: string): Promise<MimiConversation> {
  return apiRequest(`/api/mimi/conversations/${conversationId}`)
}

export function fetchMimiConversations(state: 'active' | 'archived' | 'all' = 'active'): Promise<MimiConversationPage> {
  return apiRequest(`/api/mimi/conversations?state=${state}&limit=50`)
}

export function createMimiConversation(clientId = crypto.randomUUID()): Promise<MimiConversationSummary> {
  return apiRequest('/api/mimi/conversations', {
    method: 'POST',
    headers: MIMI_WRITE_HEADERS,
    body: JSON.stringify({ client_id: clientId }),
  })
}

export function renameMimiConversation(
  conversation: MimiConversationSummary,
  title: string,
): Promise<MimiConversationSummary> {
  return apiRequest(`/api/mimi/conversations/${conversation.id}`, {
    method: 'PATCH',
    headers: MIMI_WRITE_HEADERS,
    body: JSON.stringify({ title, expected_metadata_version: conversation.metadata_version }),
  })
}

export function setMimiConversationArchived(
  conversation: MimiConversationSummary,
  archived: boolean,
): Promise<MimiConversationSummary> {
  return apiRequest(`/api/mimi/conversations/${conversation.id}/${archived ? 'archive' : 'restore'}`, {
    method: 'POST',
    headers: MIMI_WRITE_HEADERS,
    body: JSON.stringify({ expected_metadata_version: conversation.metadata_version }),
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

export type MimiStreamEnvelope = {
  event: string
  data: Record<string, unknown>
}

export async function streamMimiMessage(
  conversationId: string,
  content: string,
  expectedGeneration: number,
  clientId: string,
  onEvent: (envelope: MimiStreamEnvelope) => void,
): Promise<MimiConversation> {
  const response = await fetch(`/api/mimi/conversations/${conversationId}/messages/stream`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { ...MIMI_WRITE_HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      client_id: clientId,
      content,
      expected_generation: expectedGeneration,
    }),
  })
  return consumeMimiStream(response, onEvent)
}

async function consumeMimiStream(
  response: Response,
  onEvent: (envelope: MimiStreamEnvelope) => void,
): Promise<MimiConversation> {
  if (!response.ok) {
    let body: unknown
    try { body = await response.json() } catch { /* proxy may return non-JSON */ }
    const detail = body && typeof body === 'object' && 'detail' in body
      ? (body as { detail?: unknown }).detail
      : undefined
    throw new ApiError(
      response.status,
      typeof detail === 'string' ? detail : `Mimi stream failed (${response.status})`,
      body,
    )
  }
  if (!response.body) throw new Error('Mimi stream không có response body.')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finalSnapshot: MimiConversation | null = null

  function consume(block: string) {
    let event = 'message'
    const dataLines: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
    }
    if (!dataLines.length) return
    const data = JSON.parse(dataLines.join('\n')) as Record<string, unknown>
    onEvent({ event, data })
    if (event === 'conversation.snapshot') finalSnapshot = data as unknown as MimiConversation
  }

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done }).replaceAll('\r\n', '\n')
    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      consume(buffer.slice(0, boundary))
      buffer = buffer.slice(boundary + 2)
      boundary = buffer.indexOf('\n\n')
    }
    if (done) break
  }
  if (buffer.trim()) consume(buffer)
  if (!finalSnapshot) throw new Error('Mimi stream kết thúc trước terminal snapshot.')
  return finalSnapshot
}

export function cancelMimiRun(runId: string): Promise<{ run_id: string; state: string }> {
  return apiRequest(`/api/mimi/runs/${runId}/cancel`, {
    method: 'POST',
    headers: MIMI_WRITE_HEADERS,
    body: JSON.stringify({}),
  })
}

export function reconcileMimiRun(runId: string): Promise<{
  run_id: string
  state: string
  provider_outcome: string
  result_available: boolean
}> {
  return apiRequest(`/api/mimi/runs/${runId}/reconcile`, {
    method: 'POST',
    headers: MIMI_WRITE_HEADERS,
    body: JSON.stringify({}),
  })
}

export async function resumeMimiRun(
  runId: string,
  onEvent: (envelope: MimiStreamEnvelope) => void,
): Promise<MimiConversation> {
  const response = await fetch(`/api/mimi/runs/${runId}/resume`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { ...MIMI_WRITE_HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
  return consumeMimiStream(response, onEvent)
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
