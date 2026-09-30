import type { QueryClient } from '@tanstack/react-query'

import { flushOutbox } from '@/lib/outbox-flush'

let running: Promise<boolean> | null = null

export function requestOutboxFlush(client: QueryClient) {
  if (!running) running = flushOutbox(client).finally(() => (running = null))
  return running
}

export function startOutboxCoordinator(client: QueryClient) {
  const request = () => void requestOutboxFlush(client)
  window.addEventListener('online', request)
  window.addEventListener('focus', request)
  window.addEventListener('microsched:outbox-flush-requested', request)
  request()
  return () => {
    window.removeEventListener('online', request)
    window.removeEventListener('focus', request)
    window.removeEventListener('microsched:outbox-flush-requested', request)
  }
}
