import type { QueryClient } from '@tanstack/react-query'

import { ApiError, apiRequest, TimeoutError, UnauthenticatedError } from '@/api'
import { adapterFor } from '@/lib/outbox-adapters'
import {
  listOutbox,
  removeOutbox,
  updateOutbox,
  type OutboxRow,
  type OutboxState,
} from '@/lib/outbox-db'

const LOCK_NAME = 'microsched-outbox-flush'

type Verdict = {
  state: OutboxState | 'success'
  retryAt?: number
  code?: string
}

function machineCode(error: ApiError): string | null {
  const body = error.body
  if (!body || typeof body !== 'object' || !('detail' in body)) return null
  const detail = (body as { detail?: unknown }).detail
  return detail && typeof detail === 'object' && 'code' in detail
    ? String((detail as { code?: unknown }).code)
    : null
}

function retryAfter(error: ApiError, now: number): number | null {
  const header = error.headers.get('Retry-After')?.trim()
  if (header) {
    const seconds = Number(header)
    const delay = Number.isFinite(seconds) ? seconds * 1000 : Date.parse(header) - now
    return Number.isFinite(delay) && delay >= 0 ? delay : null
  }
  const body = error.body
  if (!body || typeof body !== 'object' || !('retry_after' in body)) return null
  const seconds = Number((body as { retry_after?: unknown }).retry_after)
  return Number.isFinite(seconds) && seconds >= 0 ? seconds * 1000 : null
}

export function classifyOutboxError(
  row: OutboxRow,
  error: unknown,
  privateUnlocked: boolean,
  now = Date.now(),
): Verdict {
  if (error instanceof UnauthenticatedError) return { state: 'auth_hold', code: 'UNAUTHENTICATED' }
  if (error instanceof TimeoutError || error instanceof TypeError) {
    return { state: 'outcome_unknown', retryAt: now + backoff(row.attempts + 1), code: 'NETWORK' }
  }
  if (!(error instanceof ApiError)) return { state: 'failed', code: 'UNKNOWN' }
  const code = machineCode(error)
  if (error.status === 401) return { state: 'auth_hold', code: code ?? 'UNAUTHENTICATED' }
  if (code === 'PRIVATE_UNLOCK_REQUIRED') return { state: 'private_hold', code }
  if (row.requires_private && !privateUnlocked && (error.status === 404 || error.status === 409)) {
    return { state: 'private_hold', code: code ?? `HTTP_${error.status}` }
  }
  if (error.status === 404 && row.method === 'DELETE') return { state: 'success' }
  if ([408, 425, 429].includes(error.status) || error.status >= 500) {
    const delay = error.status === 429 ? retryAfter(error, now) : null
    return {
      state: 'outcome_unknown',
      retryAt: now + (delay ?? backoff(row.attempts + 1)),
      code: code ?? `HTTP_${error.status}`,
    }
  }
  return { state: 'failed', code: code ?? `HTTP_${error.status}` }
}

function backoff(attempt: number) {
  return Math.min(30, 2 ** Math.max(0, attempt - 1)) * 1000
}

function privateIsUnlocked(client: QueryClient): boolean {
  const session = client.getQueryData<{ private_until?: string | null }>(['session'])
  return Boolean(session?.private_until && Date.parse(session.private_until) > Date.now())
}

async function suppressDescendants(rows: OutboxRow[], parentId: number) {
  const queue = [parentId]
  while (queue.length) {
    const id = queue.shift()!
    for (const child of rows.filter((row) => row.dependency_operation_id === id)) {
      await updateOutbox(child.operation_id!, { state: 'suppressed', last_error_code: 'PARENT_FAILED' })
      queue.push(child.operation_id!)
    }
  }
}

async function executeRow(client: QueryClient, row: OutboxRow, rows: OutboxRow[]) {
  try {
    const response = await apiRequest<unknown>(row.path, {
      method: row.method,
      body: row.body === null ? undefined : row.payload_json,
    })
    await adapterFor(row.operation_kind).reconcileSuccess(client, row, response)
    await removeOutbox([row.operation_id!])
  } catch (error) {
    const verdict = classifyOutboxError(row, error, privateIsUnlocked(client))
    if (verdict.state === 'success') {
      await removeOutbox([row.operation_id!])
      return
    }
    const attempts = verdict.state === 'outcome_unknown' ? row.attempts + 1 : row.attempts
    await updateOutbox(row.operation_id!, {
      state: verdict.state,
      attempts,
      next_attempt_at: verdict.retryAt ?? null,
      last_error_code: verdict.code ?? null,
    })
    if (verdict.state === 'failed') await suppressDescendants(rows, row.operation_id!)
  }
}

async function runFlush(client: QueryClient) {
  const rows = await listOutbox()
  const byId = new Map(rows.map((row) => [row.operation_id!, row]))
  for (const row of rows) {
    if (!['pending', 'outcome_unknown'].includes(row.state)) continue
    if (row.next_attempt_at && row.next_attempt_at > Date.now()) continue
    const parent = row.dependency_operation_id ? byId.get(row.dependency_operation_id) : null
    if (parent && parent.state !== 'failed' && parent.state !== 'suppressed') continue
    if (parent && ['failed', 'suppressed'].includes(parent.state)) {
      await updateOutbox(row.operation_id!, { state: 'suppressed', last_error_code: 'PARENT_FAILED' })
      continue
    }
    await executeRow(client, row, rows)
  }
}

export async function flushOutbox(client: QueryClient): Promise<boolean> {
  if (!navigator.onLine) return false
  if (!navigator.locks) {
    window.dispatchEvent(new Event('microsched:web-locks-unavailable'))
    return false
  }
  await navigator.locks.request(LOCK_NAME, async () => runFlush(client))
  return true
}
