import type { QueryClient } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { startOutboxCoordinator } from '@/lib/outbox-coordinator'
import { flushOutbox } from '@/lib/outbox-flush'

vi.mock('@/lib/outbox-flush', () => ({ flushOutbox: vi.fn(async () => true) }))
vi.mock('@/lib/outbox-db', () => ({ listOutbox: vi.fn(async () => []) }))

afterEach(() => vi.unstubAllGlobals())

describe('empty-queue coordinator reads', () => {
  it('does not duplicate mount or ACK refetches, but refreshes on focus', async () => {
    const target = new EventTarget()
    const documentTarget = Object.assign(new EventTarget(), { visibilityState: 'visible' })
    vi.stubGlobal('window', target)
    vi.stubGlobal('document', documentTarget)
    vi.stubGlobal('navigator', { onLine: true })
    const invalidateQueries = vi.fn(async (options: { queryKey: readonly string[] }) => { void options; return undefined })
    const stop = startOutboxCoordinator({ invalidateQueries } as unknown as QueryClient)
    try {
      await new Promise((resolve) => setTimeout(resolve, 0))
      expect(invalidateQueries).not.toHaveBeenCalled()
      target.dispatchEvent(new Event('microsched:outbox-flush-requested'))
      await new Promise((resolve) => setTimeout(resolve, 0))
      expect(invalidateQueries).not.toHaveBeenCalled()
      target.dispatchEvent(new Event('focus'))
      await new Promise((resolve) => setTimeout(resolve, 0))
      expect(invalidateQueries.mock.calls.map(([value]) => value.queryKey)).toEqual(
        ['tasks', 'notes', 'calendar', 'tracker', 'subscription'].map((family) => [family]),
      )
    } finally { stop() }
  })
})

it('coalesces overlapping reconnect and focus into one refresh after the active plan', async () => {
  const target = new EventTarget()
  const documentTarget = Object.assign(new EventTarget(), { visibilityState: 'visible' })
  vi.stubGlobal('window', target)
  vi.stubGlobal('document', documentTarget)
  vi.stubGlobal('navigator', { onLine: true })
  let release!: (value: boolean) => void
  vi.mocked(flushOutbox).mockImplementationOnce(() => new Promise<boolean>((resolve) => { release = resolve }))
  const invalidateQueries = vi.fn(async () => undefined)
  const stop = startOutboxCoordinator({ invalidateQueries } as unknown as QueryClient)
  try {
    target.dispatchEvent(new Event('online'))
    target.dispatchEvent(new Event('focus'))
    expect(invalidateQueries).not.toHaveBeenCalled()
    release(true)
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(invalidateQueries.mock.calls).toHaveLength(5)
  } finally { release(true); stop() }
})
