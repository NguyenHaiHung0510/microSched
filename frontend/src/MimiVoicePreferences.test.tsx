import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, expect, test, vi } from 'vitest'
import { fetchMimiVoicePreferences, saveMimiVoicePreferences } from './mimi-api'
import { MimiVoicePreferences } from './MimiVoicePreferences'

afterEach(() => vi.unstubAllGlobals())

test('Voice preference reads and updates only the authenticated Voice endpoint', async () => {
  const fetch = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>()
    .mockResolvedValueOnce(Response.json({ fast_apply: true }))
    .mockResolvedValueOnce(Response.json({ fast_apply: false }))
    .mockResolvedValueOnce(Response.json({ fast_apply: 'false' }))
  vi.stubGlobal('fetch', fetch)
  await expect(fetchMimiVoicePreferences()).resolves.toEqual({ fast_apply: true })
  await expect(saveMimiVoicePreferences(false)).resolves.toEqual({ fast_apply: false })
  await expect(fetchMimiVoicePreferences()).rejects.toThrow('invalid_voice_preferences')
  expect(fetch.mock.calls.map(([url]) => url)).toEqual(Array(3).fill('/api/mimi/voice-preferences'))
  expect(fetch.mock.calls[0][1]?.credentials).toBe('same-origin')
  expect(fetch.mock.calls[1][1]).toMatchObject({
    method: 'PATCH', credentials: 'same-origin',
    headers: { 'X-Mimi-CSRF': '1' }, body: '{"fast_apply":false}',
  })
})

test('settings show loading or the server preference without preselecting a write', async () => {
  const client = new QueryClient()
  const key = ['mimi', 'voice-preferences']
  const view = () => renderToStaticMarkup(<QueryClientProvider client={client}><MimiVoicePreferences /></QueryClientProvider>)
  expect(view()).toContain('Đang tải cấu hình giọng nói…')
  expect(view()).not.toContain('role="switch"')
  for (const fast_apply of [true, false]) {
    client.setQueryData(key, { fast_apply })
    expect(view()).toContain(`aria-checked="${fast_apply}"`)
    expect(view()).toContain(fast_apply ? 'Đang bật' : 'Đang tắt')
    expect(view()).toContain('tối đa 5 Task')
    expect(view()).toContain('Chat vẫn xác nhận như trước.')
  }
  client.removeQueries({ queryKey: key })
  await expect(client.fetchQuery({ queryKey: key, queryFn: async () => { throw new Error('synthetic read failure') } })).rejects.toThrow()
  expect(view()).toContain('Chưa tải được cấu hình giọng nói.')
  expect(view()).not.toContain('role="switch"')
  expect(view()).toContain('Tải lại')
  client.clear()
})
