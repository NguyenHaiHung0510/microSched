import { afterEach, expect, it, vi } from 'vitest'
import { fetchMimiSelection, recoverMimiReceipt, readMimiDevicePreference, saveMimiDevicePreference, saveMimiConfiguration, type MimiChangeSet } from './mimi-api'
afterEach(() => vi.unstubAllGlobals())
it('receipt recovery is a bounded GET bound to original nonce/digest/key; device proof stays out of URL', async () => {
  const request = vi.fn().mockResolvedValue(new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', request)
  const c = { id: 'change', digest: 'a'.repeat(64), nonce: 'nonce' } as MimiChangeSet
  await recoverMimiReceipt('conv', c, 'original-key')
  expect(request.mock.calls[0][0]).toContain('/change-sets/change/receipt?digest=')
  expect(request.mock.calls[0][1]).toMatchObject({ headers: { 'Idempotency-Key': 'original-key' } })
  expect(request.mock.calls[0][1].method).toBeUndefined()
  const proof = { subscription_id: 'subscription', endpoint: 'https://push.example/synthetic', p256dh: 'synthetic', auth: 'synthetic-auth' }
  await readMimiDevicePreference(proof)
  expect(request.mock.calls[1][0]).toBe('/api/mimi/devices/preference/read')
  expect(request.mock.calls[1][1]).toMatchObject({ method: 'POST', headers: { 'X-Mimi-CSRF': '1' }, body: JSON.stringify(proof) })
  await saveMimiDevicePreference(proof, false, 12)
  expect(JSON.parse(request.mock.calls[2][1].body)).toMatchObject({ enabled: false, expected_revision: 12 })
})
it('configuration CAS carries strictuptime and only changes next-run configuration', async () => {
  const request = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
  vi.stubGlobal('fetch', request)
  await saveMimiConfiguration('conv', { profile_id: 'deepseek', effort: 'high', input_tokens: 100000, routing_mode: 'adaptive', min_uptime_percent: 97, uptime_window: '30m' }, 9)
  expect(JSON.parse(request.mock.calls[0][1].body)).toMatchObject({ expected_version: 9, profile_id: 'deepseek', effort: 'high', min_uptime_percent: 97, uptime_window: '30m' })
  await fetchMimiSelection('conv', 'selection')
  expect(request.mock.calls[1][0]).toBe('/api/mimi/conversations/conv/selections/selection')
})
