import { afterEach, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClient, QueryClientProvider, QueryObserver } from '@tanstack/react-query'
import { LiveStatus, PrimaryLiveStatus } from './LiveStatus'
const human = vi.hoisted(() => ({ active: false }))
vi.mock('@/human-activity', () => ({ useHumanActive: () => human.active }))
vi.mock('react', async original => {
  const react = await original<typeof import('react')>()
  return { ...react, useSyncExternalStore: (_subscribe: unknown, get: () => unknown) => get() }
})
afterEach(() => { vi.unstubAllGlobals(); human.active = false })
it('A228 pauses only the miGarden Web badge on human idle; task badge retains its previous policy', () => {
  vi.stubGlobal('document', { visibilityState: 'visible' })
  const client = new QueryClient()
  client.setQueryData(['tasks', 'synthetic'], [])
  const observer = new QueryObserver(client, { queryKey: ['tasks', 'synthetic'], enabled: false })
  const stop = observer.subscribe(() => undefined)
  try {
    const output = renderToStaticMarkup(<QueryClientProvider client={client}><LiveStatus tab="tasks" /><PrimaryLiveStatus query={{ status: 'success', dataUpdatedAt: Date.now(), fetchStatus: 'idle' }} /></QueryClientProvider>)
    expect(output).toContain('data-state="live"')
    expect(output).toContain('Web · Tạm dừng cập nhật')
    expect(output.match(/data-state="paused"/g)).toHaveLength(1)
  } finally { stop(); client.clear() }
})
