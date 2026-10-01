import type { QueryClient } from '@tanstack/react-query'
import { flushOutbox } from '@/lib/outbox-flush'
import { listOutbox } from '@/lib/outbox-db'
let running: Promise<boolean> | null = null
export function requestOutboxFlush(client: QueryClient) {
  if (!running) running = flushOutbox(client).finally(() => (running = null))
  return running
}

export function startOutboxCoordinator(client: QueryClient) {
  let timer: ReturnType<typeof setTimeout> | undefined
  let stopped = false
  let planning = false
  let pendingRefresh = false
  const request = async (refreshWhenEmpty = false) => {
    if (stopped) return
    if (planning) { pendingRefresh ||= refreshWhenEmpty; return }
    planning = true
    try {
    clearTimeout(timer)
    if (stopped || !navigator.onLine || document.visibilityState === 'hidden') return
    if (!await requestOutboxFlush(client)) return
    const rows = await listOutbox()
    if (refreshWhenEmpty && !rows.length) await Promise.all(['tasks', 'notes', 'calendar', 'tracker', 'subscription'].map((family) => client.invalidateQueries({ queryKey: [family] })))
    const candidates = rows.filter((row) => ['pending', 'outcome_unknown'].includes(row.state) &&
      !rows.some((parent) => parent.operation_id === row.dependency_operation_id))
    if (!stopped && candidates.length) {
      const next = Math.min(...candidates.map((row) => row.next_attempt_at ?? Date.now()))
      timer = setTimeout(() => void request(), Math.min(2_147_483_647, Math.max(1000, next - Date.now())))
    }
    } catch { window.dispatchEvent(new Event('microsched:offline-unavailable')) } finally {
      planning = false
      if (pendingRefresh && !stopped) { pendingRefresh = false; void request(true) }
    }
  }
  const wake = (event: Event) => void request(['online', 'focus', 'visibilitychange'].includes(event.type))
  const events = ['online', 'focus', 'microsched:outbox-flush-requested', 'microsched:outbox-session-changed']
  for (const event of events) window.addEventListener(event, wake)
  document.addEventListener('visibilitychange', wake)
  void request()
  return () => {
    stopped = true
    clearTimeout(timer)
    for (const event of events) window.removeEventListener(event, wake)
    document.removeEventListener('visibilitychange', wake)
  }
}
