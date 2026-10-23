import { describe, expect, it, vi } from 'vitest'

import { QueryClient } from '@tanstack/react-query'
import {
  countdownLabel,
  expirePrivateSession,
  remainingSeconds,
} from '@/private-gate'

describe('private gate expiry controller', () => {
  it('keeps a future gate and reports the remaining countdown', () => {
    const now = Date.parse('2026-07-31T00:00:00Z')
    const queryClient = new QueryClient()
    const remove = vi.spyOn(queryClient, 'removeQueries')

    expect(remainingSeconds('2026-07-31T00:01:01Z', now)).toBe(61)
    expect(countdownLabel(61)).toBe('1:01')
    expect(expirePrivateSession(queryClient, '2026-07-31T00:01:01Z', now)).toBe(false)
    expect(remove).not.toHaveBeenCalled()
    queryClient.clear()
  })

  it('masks private responses at expiry and retains public rows instead of discarding their drafts', () => {
    const now = Date.parse('2026-07-31T00:01:01Z')
    const queryClient = new QueryClient()
    queryClient.setQueryData(['tasks','all'], {items:[{id:'public',is_private:false},{id:'hidden',is_private:true}]})
    queryClient.setQueryData(['reminders','target','private'], {id:'private',is_private:true,source_title:'canary'})
    queryClient.setQueryData(['session'], {private_until:'2026-07-31T00:01:01Z'})

    expect(expirePrivateSession(queryClient, '2026-07-31T00:01:01Z', now)).toBe(true)
    expect(queryClient.getQueryData(['tasks','all'])).toMatchObject({items:[{id:'public'}]})
    expect(queryClient.getQueryData(['reminders','target','private'])).toBeUndefined()
    expect(queryClient.getQueryData(['session'])).toEqual({private_until:null})
    queryClient.clear()
  })
})
