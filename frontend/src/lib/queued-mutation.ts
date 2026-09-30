import type { QueryClient } from '@tanstack/react-query'

import { ApiError, apiRequest, TimeoutError } from '@/api'
import { adapterFor, type CommandInput, type OperationKind } from '@/lib/outbox-adapters'
import { enqueueOutbox, type Json, type OutboxRow } from '@/lib/outbox-db'

function isTransportError(error: unknown) {
  return error instanceof TimeoutError || error instanceof TypeError
}

export async function queuedRequest<T>(
  client: QueryClient,
  operationKind: OperationKind,
  input: CommandInput,
  init?: { timeoutMs?: number },
): Promise<T> {
  const adapter = adapterFor(operationKind)
  const body = input.body ?? null
  const base: Omit<
    OutboxRow,
    'operation_id' | 'payload_json' | 'payload_sha256' | 'payload_byte_length'
  > = {
    operation_kind: operationKind,
    resource: adapter.resource,
    method: adapter.method,
    path: input.path,
    body,
    entity_id: input.entityId ?? entityIdFromBody(body),
    parent_id: input.parentId ?? null,
    requires_private: input.requiresPrivate ?? false,
    idempotency_mode: adapter.idempotencyMode,
    dependency_operation_id: input.dependencyOperationId ?? null,
    group_id: input.groupId ?? null,
    affected_query_keys: adapter.affectedQueryKeys(input).map((key) => [...key] as Json[]),
    state: 'pending',
    attempts: 0,
    next_attempt_at: null,
    created_at: Date.now(),
    last_error_code: null,
  }

  if (navigator.onLine) {
    try {
      const response = await apiRequest<T>(input.path, {
        method: adapter.method,
        body: body === null ? undefined : JSON.stringify(body),
        timeoutMs: init?.timeoutMs,
      })
      await adapter.reconcileSuccess(
        client,
        { ...base, payload_json: '', payload_sha256: '', payload_byte_length: 0 },
        response,
      )
      return response
    } catch (error) {
      if (!isTransportError(error)) throw error
      base.state = 'outcome_unknown'
      base.attempts = 1
      base.next_attempt_at = Date.now() + 1000
      base.last_error_code = error instanceof TimeoutError ? 'TIMEOUT' : 'NETWORK'
    }
  }

  const row = await enqueueOutbox(base)
  if (!row) throw new ApiError(507, 'Không thể lưu ngoại tuyến')
  await adapter.optimisticApply(client, row)
  window.dispatchEvent(new Event('microsched:outbox-flush-requested'))
  return adapter.optimisticResponse(row) as T
}

function entityIdFromBody(body: Json | null): string | null {
  if (!body || Array.isArray(body) || typeof body !== 'object') return null
  return typeof body.id === 'string' ? body.id : null
}
