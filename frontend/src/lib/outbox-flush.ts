import type { QueryClient } from '@tanstack/react-query'
import { ApiError, apiRequest, TimeoutError, UnauthenticatedError } from '@/api'
import { adapterFor } from '@/lib/outbox-adapters'
import {
  listOutbox,
  claimOutbox,
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

function privateIsUnlocked(client: QueryClient) {
  const session = client.getQueryData<{ private_until?: string | null }>(['session'])
  return Boolean(session?.private_until && Date.parse(session.private_until) > Date.now())
}

async function runFlush(client: QueryClient) {
  const rows = await listOutbox()
  const active = new Map(rows.map((row) => [row.operation_id!, row]))
  const touched = new Map<string, readonly unknown[]>()
  for (const row of rows) {
    if (!navigator.onLine) break
    if (['failed', 'suppressed'].includes(row.state)) continue
    const parent = row.dependency_operation_id ? active.get(row.dependency_operation_id) : null
    if (parent) {
      if (['failed', 'suppressed'].includes(parent.state)) {
        row.state = 'suppressed'
        await updateOutbox(row.operation_id!, { state: 'suppressed', last_error_code: 'PARENT_FAILED' })
      }
      continue
    }
    const unlocked = privateIsUnlocked(client)
    if (row.requires_private && !unlocked) {
      await updateOutbox(row.operation_id!, { state: 'private_hold' })
      continue
    }
    if (row.state === 'auth_hold' && (client.getQueryData<{ offline_bootstrap?: boolean }>(['session'])?.offline_bootstrap || (client.getQueryState(['session'])?.dataUpdatedAt ?? 0) <= (row.next_attempt_at ?? Infinity))) continue
    if (row.state === 'private_hold' && !unlocked) continue
    if (row.state === 'auth_hold' || row.state === 'private_hold') {
      row.next_attempt_at = null
      await updateOutbox(row.operation_id!, { state: 'pending' })
    }
    if (row.next_attempt_at && row.next_attempt_at > Date.now()) continue
    await Promise.all(row.affected_query_keys.map((queryKey) => client.cancelQueries({ queryKey })))
    const claimed = await claimOutbox(row.operation_id!)
    if (!claimed) continue
    if (!navigator.onLine || (claimed.requires_private && !privateIsUnlocked(client))) {
      await updateOutbox(claimed.operation_id!, { state: navigator.onLine ? 'private_hold' : 'pending', attempts: row.attempts })
      window.dispatchEvent(new CustomEvent('microsched:outbox-not-attempted', { detail: { operation_id: claimed.operation_id } }))
      continue
    }
    let response: unknown, acknowledged = false
    try {
      response = await apiRequest<unknown>(claimed.path, { method: claimed.method,
        body: claimed.body === null ? undefined : claimed.payload_json, timeoutMs: claimed.timeout_ms })
      acknowledged = true
    } catch (error) {
      const verdict = classifyOutboxError(row, error, privateIsUnlocked(client))
      if (verdict.state === 'success') acknowledged = true
      else {
        row.state = verdict.state; if (verdict.state === 'private_hold') window.dispatchEvent(new Event('microsched:private-locked'))
        await updateOutbox(claimed.operation_id!, { state: verdict.state,
          attempts: ['auth_hold', 'private_hold'].includes(verdict.state) ? row.attempts : claimed.attempts,
          next_attempt_at: verdict.state === 'auth_hold' ? Date.now() : verdict.retryAt ?? null, last_error_code: verdict.code ?? null })
      }
    }
    if (acknowledged) {
      await removeOutbox([claimed.operation_id!])
      active.delete(claimed.operation_id!)
      try { await adapterFor(claimed.operation_kind).reconcileSuccess(client, claimed, response) }
      catch { window.dispatchEvent(new Event('microsched:outbox-reconcile-unavailable')) }
      for (const key of claimed.affected_query_keys) touched.set(JSON.stringify(key), key)
    }
  }
  const remaining = await listOutbox()
  for (const key of touched.values()) {
    if (!remaining.some((row) => row.affected_query_keys.some((affected) =>
      affected.slice(0, Math.min(affected.length, key.length)).every((part, index) => key[index] === part)))) await client.invalidateQueries({ queryKey: key })
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
