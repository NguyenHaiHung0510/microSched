import { describe, expect, it, vi } from 'vitest'

import { taskInvalidationKey } from '@/task-ui'
import {
  countdownLabel,
  expirePrivateSession,
  remainingSeconds,
} from '@/private-gate'

describe('private gate expiry controller', () => {
  it('keeps a future gate and reports the remaining countdown', () => {
    const now = Date.parse('2026-07-31T00:00:00Z')
    const queryClient = { removeQueries: vi.fn() }

    expect(remainingSeconds('2026-07-31T00:01:01Z', now)).toBe(61)
    expect(countdownLabel(61)).toBe('1:01')
    expect(expirePrivateSession(queryClient, '2026-07-31T00:01:01Z', now)).toBe(false)
    expect(queryClient.removeQueries).not.toHaveBeenCalled()
  })

  it('removes the exact task query prefix at and after expiry', () => {
    const now = Date.parse('2026-07-31T00:01:01Z')
    const queryClient = { removeQueries: vi.fn() }

    expect(expirePrivateSession(queryClient, '2026-07-31T00:01:01Z', now)).toBe(true)
    expect(queryClient.removeQueries).toHaveBeenCalledTimes(2)
    expect(queryClient.removeQueries).toHaveBeenCalledWith({
      queryKey: taskInvalidationKey,
    })
  })
})
