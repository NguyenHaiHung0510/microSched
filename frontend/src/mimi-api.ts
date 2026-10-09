import { ApiError, apiRequest } from '@/api'

export type MimiMessageProvenance = {
  origin: 'model_answer' | 'server_notice' | 'unknown'
  producer_code: string | null
  version: 1 | null
  event_sequence: number | null
  source: 'server_verified' | 'absent_or_unverified'
}

export type MimiMessage = {
  provenance?: MimiMessageProvenance
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
  resumable?: boolean
  created_at: string
  completed_at: string | null
}

export type MimiConfirmationPreflight = { status: 'eligible' | 'blocked'; reason: string | null }

export type MimiChangeSet = {
  // Snapshot eligibility only; POST still validates the frozen binding and source CAS.
  confirmation_preflight?: MimiConfirmationPreflight
  id: string
  run_id: string
  state: string
  digest: string
  nonce: string
  expires_at: string
  policy_version: string
  operation: ({
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
  } | { operation_id: string; tool: 'task.collection.v1'; args: MimiCollectionPlan })
}

export type MimiReceipt = {
  id: string
  change_set_id: string
  operation_id: string
  task_id: string | null
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
  evidence_bundle_ids?: string[]
}

export type MimiFeedbackTarget = {
  target_type: 'turn' | 'run' | 'call' | 'operation' | 'receipt'
  target_id: string
  label: string
}

export type MimiEvent = {
  id: string
  run_id: string
  sequence: number
  kind: string
  payload: Record<string, unknown>
  created_at: string
}

export type MimiDraftDirection = {
  id: string
  revision: number
  content_sha256: string
  direction_state: 'pending' | 'approved' | 'rejected'
}

export type MimiProviderCall = {
  id: string
  run_id: string
  attempt: number
  state: string
  requested_model: string | null
  requested_effort: string | null
  actual_model: string | null
  actual_provider: string | null
  usage: Record<string, number>
  purpose?: 'main' | 'compaction'
  context_revision?: string | null
  paid_dispatch?: boolean
  response_id?: string | null
  cost_state?: 'reported' | 'unknown'
  created_at?: string
}

export type MimiContextObservation = {
  prompt_tokens: number | null
  source_call_id: string | null
  context_revision: string
  trigger_tokens: number
  eligible: boolean
  should_compact: boolean
  compaction_blocked?: boolean
  reason: string
}

export type MimiRunObservation = {
  known_cost_usd: number
  main_known_cost_usd: number
  helper_known_cost_usd: number
  unknown_cost_calls: number
  main_unknown_cost_calls: number
  helper_unknown_cost_calls: number
  cost_complete: boolean
  receipts_truncated?: boolean
  main_calls: number
  helper_calls: number
  reused_calls: number
  elapsed_ms: number | null
  context_observations: MimiContextObservation[]
  checkpoint_activations: number
  error_code: string | null
}

export type MimiCapabilities = {
  collection_enabled?: boolean
  notifications_enabled?: boolean
  context_v1_enabled: boolean
  workflow_pilot_enabled: boolean
  live_provider_enabled: boolean
  requested_model: string | null
  requested_effort: string | null
  route_mode: string | null
  model_selection_enabled: boolean
  context_limit: number
  output_reserve: number
  policy_id: string | null
  policy_sha256: string | null
  model_profiles?: MimiModelProfile[]
  conversation_planning_mode?: 'prose' | string
  runner?: 'langgraph' | 'current' | string
  context_policy?: string
  compaction_trigger_tokens?: number
  payload_limit_bytes?: number
}

export type MimiModelProfile = {
  id: string
  label: string
  model: string
  provider: string
  quantization: string
  supported_efforts: string[]
  context_limit: number
  output_reserve: number
  available: boolean
  unavailable_reason: string | null
  evidence?: string
  compaction_trigger_tokens?: number
}

export type MimiRouteConfig = {
  profile_id: string
  effort: string
  input_tokens: number
  routing_mode?: 'exact' | 'adaptive'
  min_uptime_percent?: number
  uptime_window?: '1d' | '30m'
}

export type MimiConversationConfiguration = {
  config: MimiRouteConfig
  version: number
  applies_to: 'next_run'
  active_run_id: string | null
  profiles: MimiModelProfile[]
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
  draft?: MimiDraftDirection | null
  provider_calls?: MimiProviderCall[]
  run_observations?: Record<string, MimiRunObservation>
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

export function fetchMimiCapabilities(): Promise<MimiCapabilities> {
  return apiRequest('/api/mimi/capabilities')
}

export function fetchMimiConfiguration(conversationId: string): Promise<MimiConversationConfiguration> {
  return apiRequest(`/api/mimi/conversations/${conversationId}/configuration`)
}

export function saveMimiConfiguration(
  conversationId: string,
  config: MimiRouteConfig,
  expectedVersion: number,
): Promise<MimiConversationConfiguration> {
  return apiRequest(`/api/mimi/conversations/${conversationId}/configuration`, {
    method: 'PUT',
    headers: MIMI_WRITE_HEADERS,
    body: JSON.stringify({
      expected_version: expectedVersion,
      profile_id: config.profile_id,
      effort: config.effort,
      input_tokens: config.input_tokens,
      routing_mode: config.routing_mode ?? 'adaptive',
      min_uptime_percent: config.min_uptime_percent ?? 95,
      uptime_window: config.uptime_window ?? '1d',
    }),
  })
}

export function decideMimiDraftDirection(
  conversationId: string,
  draft: MimiDraftDirection,
  decision: 'approve' | 'reject',
): Promise<{ draft_id: string; state: string }> {
  return apiRequest(`/api/mimi/conversations/${conversationId}/draft-direction`, {
    method: 'POST',
    headers: MIMI_WRITE_HEADERS,
    body: JSON.stringify({
      draft_id: draft.id,
      expected_revision: draft.revision,
      expected_content_sha256: draft.content_sha256,
      decision,
    }),
  })
}

export function fetchCurrentMimiConversation(): Promise<MimiConversation | null> {
  return apiRequest('/api/mimi/conversations/current')
}

export type MimiCheckpointConstraint = {
  id: string
  text: string
  kind: string
  status: 'active' | 'superseded' | 'resolved'
  source?: { sequence?: number; quote?: string; sha256?: string; legacy_checkpoint_sha256?: string }
}

export type MimiCheckpointView = {
  conversation_id: string
  checkpoint_id: string | null
  frontier: number
  checkpoint_sha256: string | null
  activated_at: string | null
  checkpoint: {
    summary: string
    summary_kind: string
    constraint_ledger?: MimiCheckpointConstraint[]
    decisions: string[]
    unresolved: string[]
    source_refs: { id: string; sequence: number; sha256: string }[]
  } | null
}

export function fetchMimiCheckpoint(conversationId: string): Promise<MimiCheckpointView> {
  return apiRequest(`/api/mimi/conversations/${conversationId}/context`)
}

export function fetchMimiConversation(conversationId: string): Promise<MimiConversation> {
  return apiRequest(`/api/mimi/conversations/${conversationId}`)
}

export function fetchMimiConversations(state: 'active' | 'archived' | 'all' = 'active', cursor?: string | null): Promise<MimiConversationPage> {
  const suffix = cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''
  return apiRequest(`/api/mimi/conversations?state=${state}&limit=50${suffix}`)
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
  revision: { id: string; digest: string } | null,
  onEvent: (envelope: MimiStreamEnvelope) => void,
): Promise<MimiConversation> {
  return boundedMimiStream(`/api/mimi/conversations/${conversationId}/messages/stream`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { ...MIMI_WRITE_HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      client_id: clientId,
      content,
      expected_generation: expectedGeneration,
      intent: revision ? 'revise_pending_preview' : 'auto',
      ...(revision ? {
        expected_change_set_id: revision.id,
        expected_change_set_digest: revision.digest,
      } : {}),
    }),
  }, onEvent)
}

// Admission is bounded20s; observation may last the existing server maximum2h.
// Disconnect only stops observing: never cancels, replays or infers provider failure.
async function boundedMimiStream(path: string, init: RequestInit, onEvent: (envelope: MimiStreamEnvelope) => void): Promise<MimiConversation> {
  const controller = new AbortController()
  const caller = init.signal
  const abort = () => controller.abort(caller?.reason)
  if (caller?.aborted) abort()
  else caller?.addEventListener('abort', abort, { once: true })
  const admission = setTimeout(() => controller.abort(new DOMException('Mimi admission timed out', 'TimeoutError')), 20_000)
  const observation = setTimeout(() => controller.abort(new DOMException('Mimi observation limit reached', 'TimeoutError')), 7_220_000)
  try {
    const response = await fetch(path, { ...init, signal: controller.signal })
    clearTimeout(admission)
    return await consumeMimiStream(response, onEvent)
  } finally {
    clearTimeout(admission)
    clearTimeout(observation)
    caller?.removeEventListener('abort', abort)
  }
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

  try {
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
  } finally { reader.releaseLock() }
}

export async function observeMimiRun(
  runId: string,
  onEvent: (envelope: MimiStreamEnvelope) => void,
  signal?: AbortSignal,
): Promise<MimiConversation> {
  return boundedMimiStream(`/api/mimi/runs/${runId}/events/stream?after=0`, {
    method: 'GET',
    credentials: 'same-origin',
    signal,
  }, onEvent)
}

export function cancelMimiRun(runId: string): Promise<{ run_id: string; state: string }> {
  return apiRequest(`/api/mimi/runs/${runId}/cancel`, {
    method: 'POST',
    headers: MIMI_WRITE_HEADERS,
    body: JSON.stringify({}),
  })
}

export type MimiPauseAcknowledgment = {
  run_id: string
  state: string
  pause_requested: true
}

export function pauseMimiRun(runId: string): Promise<MimiPauseAcknowledgment> {
  return apiRequest(`/api/mimi/runs/${runId}/pause`, {
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
  return boundedMimiStream(`/api/mimi/runs/${runId}/resume`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { ...MIMI_WRITE_HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  }, onEvent)
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
  target: Pick<MimiFeedbackTarget, 'target_type' | 'target_id'>,
  comment: string,
  expected: string,
  clientId: string,
): Promise<MimiFeedback> {
  return apiRequest(`/api/mimi/conversations/${conversationId}/feedback`, {
    method: 'POST',
    headers: MIMI_WRITE_HEADERS,
    body: JSON.stringify({
      client_id: clientId,
      target_type: target.target_type,
      target_id: target.target_id,
      comment,
      expected: expected.trim() || null,
      evidence_bundle_ids: [],
    }),
  })
}


export type MimiTaskSnapshot = {
  fields: Record<string, unknown>
  children: Array<{ id: string; content: string; is_completed: boolean; position: number; deleted_at?: string | null }>
  deleted_at?: string | null
  collection_version?: number
  reminder?: Record<string, unknown> | null
}
export type MimiCollectionEntry = {
  id: string
  command: { action: 'create' | 'edit' | 'soft_delete' | 'restore'; expected_collection_version: number | null; fields: Record<string, unknown>; children: Array<Record<string, unknown>>; reminder: Record<string, unknown> }
  before: MimiTaskSnapshot | null
  after: MimiTaskSnapshot
  reminder_effect: Record<string, unknown>
}
export type MimiCollectionPlan = {
  schema_version: 'mimi.task-collection.v1'
  selection_id: string | null
  entries: MimiCollectionEntry[]
  undo_receipt_id?: string | null
}
export type MimiSelection = {
  selection_id: string
  intent: string
  variants_considered: string[]
  variants_pending: string[]
  unproved_variants: string[]
  members: Array<{ id: string; classification: 'included' | 'excluded' | 'uncertain'; reason: string; collection_version: number }>
  query_complete: boolean
  semantic_complete: boolean
  explicitly_named_subset: boolean
  as_of: string
}
export function fetchMimiSelection(conversationId: string, selectionId: string): Promise<MimiSelection> {
  return apiRequest(`/api/mimi/conversations/${conversationId}/selections/${selectionId}`)
}
export function recoverMimiReceipt(conversationId: string, change: MimiChangeSet, key: string): Promise<MimiReceipt> {
  const params = new URLSearchParams({ digest: change.digest, nonce: change.nonce })
  return apiRequest(`/api/mimi/conversations/${conversationId}/change-sets/${change.id}/receipt?${params}`, { headers: { 'Idempotency-Key': key } })
}
export function prepareMimiUndo(receiptId: string): Promise<MimiConversation> {
  return apiRequest(`/api/mimi/receipts/${receiptId}/undo-preview`, { method: 'POST', headers: MIMI_WRITE_HEADERS, body: '{}' })
}
export function fetchMimiEvidence(conversationId: string, bundleId: string): Promise<Record<string, unknown>> {
  return apiRequest(`/api/mimi/conversations/${conversationId}/evidence/${bundleId}`)
}
export type MimiAttention = { id: string; conversation_id: string; run_id: string; title: string; body: string; kind: string; unread: boolean; expires_at: string }
export function fetchMimiAttention(): Promise<MimiAttention[]> { return apiRequest('/api/mimi/attention') }
export function acknowledgeMimiAttention(id: string): Promise<{ id: string; unread: false }> {
  return apiRequest(`/api/mimi/attention/${id}/read`, { method: 'POST', headers: MIMI_WRITE_HEADERS, body: '{}' })
}
export function resolveMimiAttention(locator: string): Promise<{ conversation_id: string; run_id: string; expired: boolean }> {
  return apiRequest(`/api/mimi/attention/resolve/${encodeURIComponent(locator)}`)
}
export type MimiDeviceProof = { subscription_id: string; endpoint: string; p256dh: string; auth: string }
export type MimiDevicePreference = { subscription_id: string; enabled: boolean; revision: number | null; registered?: boolean }
export function readMimiDevicePreference(proof: MimiDeviceProof): Promise<MimiDevicePreference> {
  return apiRequest('/api/mimi/devices/preference/read', { method: 'POST', headers: MIMI_WRITE_HEADERS, body: JSON.stringify(proof) })
}
export function saveMimiDevicePreference(proof: MimiDeviceProof, enabled: boolean, expectedRevision: number | null): Promise<MimiDevicePreference> {
  return apiRequest('/api/mimi/devices/preference', { method: 'POST', headers: MIMI_WRITE_HEADERS, body: JSON.stringify({ ...proof, enabled, expected_revision: expectedRevision }) })
}
export type MimiProviderPool = {
  model: string
  effort: string
  tags: string[]
  checked_at: number
  snapshot_sha256: string
  min_uptime_percent: number
  window: string
  exclusions: string[]
  qualification: string
}
export function refreshMimiProviderPool(conversationId: string): Promise<MimiProviderPool> {
  return apiRequest(`/api/mimi/conversations/${conversationId}/provider-pool/refresh`, { method: 'POST', headers: MIMI_WRITE_HEADERS, body: '{}', timeoutMs: 15_000 })
}
