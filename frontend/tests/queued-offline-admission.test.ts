import { MutationObserver, onlineManager, QueryClient } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { QUEUED_MUTATION_OPTIONS } from '@/lib/queued-mutation'

describe('offline domain mutation admission', () => {
  it('runs the durable write seam immediately while offline, without changing the default online-only policy', async () => {
    const client = new QueryClient()
    client.mount()
    onlineManager.setOnline(false)
    const queued = vi.fn(async () => 'durable-command')
    const auth = vi.fn(async () => 'online-only')
    const domain = new MutationObserver(client, { ...QUEUED_MUTATION_OPTIONS, mutationFn: queued })
    const authentication = new MutationObserver(client, { mutationFn: auth })
    const pending = domain.mutate()
    const authPending = authentication.mutate()
    try {
      await new Promise((resolve) => setTimeout(resolve, 0))
      expect(queued).toHaveBeenCalledOnce()
      expect(domain.getCurrentResult().isPaused).toBe(false)
      expect(domain.getCurrentResult().data).toBe('durable-command')
      expect(auth).not.toHaveBeenCalled()
      expect(authentication.getCurrentResult().isPaused).toBe(true)
    } finally {
      onlineManager.setOnline(true)
      await client.resumePausedMutations()
      await Promise.all([pending, authPending])
      client.unmount()
      client.clear()
    }
  })
})
