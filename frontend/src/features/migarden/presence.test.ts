import { afterEach, expect, it, vi } from 'vitest'
import { gardenPresenceHeaders, listenGardenActivity, markGardenActivity } from './presence'
import { gardenStateInterval, type GardenState } from './api'
import { explainReason, historyLabel, statusLabels } from './presentation'

afterEach(() => vi.unstubAllGlobals())

it('consumes activity once; passive visible polling does not renew the server lease', () => {
  const target = new EventTarget()
  let visibilityState = 'visible'
  vi.stubGlobal('window', target)
  vi.stubGlobal('document', { get visibilityState() { return visibilityState } })
  const cleanup = listenGardenActivity()
  expect(gardenPresenceHeaders()).toEqual({ 'X-MiGarden-Visible': '1', 'X-MiGarden-Active-For': '300' })
  for (let i = 0; i < 40; i++) expect(gardenPresenceHeaders()).toEqual({})
  target.dispatchEvent(new Event('pointerdown'))
  expect(gardenPresenceHeaders()).toEqual({ 'X-MiGarden-Visible': '1', 'X-MiGarden-Active-For': '300' })
  visibilityState = 'hidden'
  markGardenActivity()
  expect(gardenPresenceHeaders()).toEqual({})
  visibilityState = 'visible'
  target.dispatchEvent(new Event('visibilitychange'))
  expect(gardenPresenceHeaders()).toEqual({ 'X-MiGarden-Visible': '1', 'X-MiGarden-Active-For': '300' })
  cleanup()
  target.dispatchEvent(new Event('keydown'))
  expect(gardenPresenceHeaders()).toEqual({})
})

it('keeps background paused, configured foreground 1s, and error/unconfigured 30s', () => {
  const configured = { connection: 'fresh' } as GardenState
  expect(gardenStateInterval(configured, 'success', true)).toBe(1_000)
  expect(gardenStateInterval(configured, 'success', false)).toBe(false)
  expect(gardenStateInterval(configured, 'error', true)).toBe(30_000)
  expect(gardenStateInterval({ connection: 'unconfigured' } as GardenState, 'success', true)).toBe(30_000)
})

it('keeps recovery and requested STOP distinct from measured completion', () => {
  expect(statusLabels.stop_requested).not.toBe(statusLabels.stop_confirmed)
  expect(statusLabels.recovered).toBe('Đã đối soát sau khởi động lại')
  expect(historyLabel({ kind: 'recovered' } as never)).toBe('Phục hồi sau khởi động lại')
  expect(explainReason('REBOOT_INTERRUPTED_RECOVERED')).toContain('thời lượng thực tế vẫn chưa rõ')
})
