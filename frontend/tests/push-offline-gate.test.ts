import { afterEach, expect, it, vi } from 'vitest'
const { apiRequest } = vi.hoisted(() => ({ apiRequest: vi.fn(async () => { throw new Error('Unexpected offline request') }) }))
vi.mock('@/api', () => ({ apiRequest }))
import { ensurePushSubscription, preparePushRegistration } from '@/push-subscription'
afterEach(() => vi.unstubAllGlobals())
it('rejects offline device registration before any browser permission or server request', async () => {
  const requestPermission = vi.fn(async () => 'granted')
  vi.stubGlobal('Notification', { requestPermission })
  vi.stubGlobal('window', { Notification: {}, matchMedia: () => ({ matches: false }) })
  vi.stubGlobal('navigator', { onLine: false, platform: 'Win32', maxTouchPoints: 0, serviceWorker: { ready: Promise.resolve({}) } })
  const error = await ensurePushSubscription().catch((caught: unknown) => caught)
  expect(requestPermission).not.toHaveBeenCalled()
  expect(apiRequest).not.toHaveBeenCalled()
  expect(error).toBeInstanceOf(Error)
  expect((error as Error).message).toContain('Cần kết nối mạng')
})

it('defers only device registration so an offline tracker domain write can proceed', async () => {
  const requestPermission = vi.fn()
  vi.stubGlobal('Notification', { requestPermission })
  vi.stubGlobal('navigator', { onLine: false })
  apiRequest.mockClear()
  await expect(preparePushRegistration(true)).resolves.toBe('offline_deferred')
  await expect(preparePushRegistration(false)).resolves.toBe('not_needed')
  expect(requestPermission).not.toHaveBeenCalled()
  expect(apiRequest).not.toHaveBeenCalled()
})
