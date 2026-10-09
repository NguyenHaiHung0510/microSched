import { afterEach, expect, it, vi } from 'vitest'
import { clearMimiIntent, hasAuthoritativeMimiRefusal, readMimiIntent, saveMimiIntent } from './mimi-recovery'
import type { MimiChangeSet } from './mimi-api'
afterEach(() => vi.unstubAllGlobals())
it('reload recovers exactly the original binding and key, never conversation prose', () => {
  const store = new Map<string, string>()
  vi.stubGlobal('sessionStorage', { setItem: (k: string, v: string) => store.set(k,v), getItem: (k: string) => store.get(k), removeItem: (k: string) => store.delete(k) })
  const change = { id: 'c', digest: 'digest-a', nonce: 'n', operation: { args: { body_md: 'SYNTHETIC_PROSE_MUST_NOT_STORE' } } } as MimiChangeSet
  saveMimiIntent({ conversationId: 'owner-conv', changeSet: change, choice: 'confirm', key: 'original-key' })
  expect([...store.values()].join('')).not.toContain('SYNTHETIC_PROSE_MUST_NOT_STORE')
  expect(readMimiIntent('owner-conv', [change])?.key).toBe('original-key')
  expect(readMimiIntent('other-conv', [change])).toBeNull()
  expect(readMimiIntent('owner-conv', [{ ...change, digest: 'superseded' }])).toBeNull()
  clearMimiIntent('owner-conv'); expect(readMimiIntent('owner-conv', [change])).toBeNull()
})

it('only a matching terminal server binding proves refusal; absence/changed nonce/digest/pending are UNKNOWN', () => {
  const c={id:'c',digest:'d',nonce:'n',state:'pending'} as MimiChangeSet
  const intent={conversationId:'owner-conv',changeSet:c,choice:'confirm' as const,key:'same-key'}
  expect(hasAuthoritativeMimiRefusal(intent,[{...c,state:'stale'}])).toBe(true)
  expect(hasAuthoritativeMimiRefusal(intent,[])).toBe(false)
  expect(hasAuthoritativeMimiRefusal(intent,[c])).toBe(false)
  expect(hasAuthoritativeMimiRefusal(intent,[{...c,state:'stale',nonce:'other'}])).toBe(false)
  expect(hasAuthoritativeMimiRefusal(intent,[{...c,state:'stale',digest:'other'}])).toBe(false)
  expect(hasAuthoritativeMimiRefusal(intent,[{...c,state:'executed'}])).toBe(false)
})
