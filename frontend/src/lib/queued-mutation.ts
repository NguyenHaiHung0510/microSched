import type { QueryClient } from '@tanstack/react-query'
import { ApiError, apiRequest } from '@/api'
import { adapterFor, type CommandInput, type OperationKind } from '@/lib/outbox-adapters'
import { enqueueOutbox, payloadReceipt, type Json, type OutboxRow } from '@/lib/outbox-db'
import { persistConfirmedSnapshot } from '@/lib/public-cache'
export type QueuedDeleteReceipt = { cancelledRows: OutboxRow[] }
export async function queuedRequest<T>(
  client: QueryClient, operationKind: OperationKind, input: CommandInput,
  init?: { timeoutMs?: number },
): Promise<T> {
  const adapter = adapterFor(operationKind)
  const encoded = adapter.encodeCommand({ ...input, operationKind })
  try { await persistConfirmedSnapshot(client) } catch { window.dispatchEvent(new Event('microsched:offline-unavailable')) }
  const command = {
    ...encoded, affected_query_keys: encoded.affected_query_keys.map((key) => [...key] as Json[]),
    state: 'pending' as const, attempts: 0, next_attempt_at: null, created_at: Date.now(),
    last_error_code: null, timeout_ms: init?.timeoutMs,
  }
  const row = await enqueueOutbox(command)
  if (!row) {
    if (!navigator.onLine) throw new ApiError(507, 'Không thể lưu ngoại tuyến')
    const confirmed = await apiRequest<T>(encoded.path, { method: encoded.method,
      body: encoded.body === null ? undefined : JSON.stringify(encoded.body), timeoutMs: init?.timeoutMs })
    try { await adapter.reconcileSuccess(client, { ...command, ...await payloadReceipt(command.body) }, confirmed) }
    catch { window.dispatchEvent(new Event('microsched:outbox-reconcile-unavailable')) }
    await Promise.all(encoded.affected_query_keys.map((queryKey) => client.invalidateQueries({ queryKey })))
    return confirmed
  }
  await adapter.optimisticApply(client, row)
  window.dispatchEvent(new Event('microsched:outbox-flush-requested'))
  if (row.cancelled_rows) return { cancelledRows: row.cancelled_rows } as T
  return adapter.optimisticResponse(row) as T
}
