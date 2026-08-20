import type { QueryClient } from '@tanstack/react-query'

import { ApiError, apiRequest } from '@/api'
import { taskInvalidationKey } from '@/task-ui'

export type PrivateSessionState = {
  email: string
  private_until: string | null
  private_locked_until: string | null
  pin_is_set: boolean
  pin_is_bootstrap: boolean
}

export type PrivateErrorDetails = {
  status: number
  message: string
  remaining?: number
  retryAfterSeconds?: number
}

export async function unlockPrivate(pin: string): Promise<{ private_until: string }> {
  return apiRequest('/api/private/unlock', {
    method: 'POST',
    body: JSON.stringify({ pin }),
  })
}

export async function lockPrivate(): Promise<void> {
  await apiRequest('/api/private/lock', { method: 'POST' })
}

export async function changePrivatePin(
  currentPin: string | null,
  newPin: string,
): Promise<void> {
  await apiRequest('/api/private/pin', {
    method: 'POST',
    body: JSON.stringify({ current_pin: currentPin, new_pin: newPin }),
  })
}

export function privateError(error: unknown): PrivateErrorDetails | null {
  if (!(error instanceof ApiError)) return null
  const body = error.body
  const values = body && typeof body === 'object' ? body : {}
  const remaining = 'remaining' in values ? Number(values.remaining) : undefined
  const retryAfterSeconds =
    'retry_after_seconds' in values ? Number(values.retry_after_seconds) : undefined
  return {
    status: error.status,
    message: error.message,
    remaining: Number.isFinite(remaining) ? remaining : undefined,
    retryAfterSeconds: Number.isFinite(retryAfterSeconds)
      ? retryAfterSeconds
      : undefined,
  }
}

export function remainingSeconds(until: string | null, now = Date.now()): number {
  if (!until) return 0
  const deadline = Date.parse(until)
  if (!Number.isFinite(deadline)) return 0
  return Math.max(0, Math.ceil((deadline - now) / 1000))
}

export function countdownLabel(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds))
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, '0')}`
}

/**
 * Remove all task responses at the instant the hard server deadline expires.
 * The boolean lets the component flip its badge without making this pure seam
 * depend on React or a DOM clock.
 */
export function expirePrivateSession(
  queryClient: Pick<QueryClient, 'removeQueries'>,
  privateUntil: string | null,
  now = Date.now(),
): boolean {
  if (!privateUntil || remainingSeconds(privateUntil, now) > 0) return false
  queryClient.removeQueries({ queryKey: taskInvalidationKey })
  queryClient.removeQueries({ queryKey: ['calendar'] })
  return true
}
