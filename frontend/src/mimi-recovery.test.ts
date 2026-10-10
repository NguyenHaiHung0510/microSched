import { afterEach, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { clearMimiIntent, hasAuthoritativeMimiRefusal, publishAuthoritativeMimiRefusal, readMimiIntent, saveMimiIntent } from './mimi-recovery'
import type { MimiChangeSet, MimiConversation } from './mimi-api'
import { collectionConfirmationNotice } from './mimi-collection'
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

it('publishes matching blocked snapshot before intent release and prevents inflight eligible data returning', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry:false, gcTime:0 } } })
  const c={id:'c',digest:'d',nonce:'n',state:'pending',confirmation_preflight:{status:'eligible',reason:null}} as MimiChangeSet
  const intent={conversationId:'owner-conv',changeSet:c,choice:'confirm' as const,key:'same-key'}
  const before={id:intent.conversationId,change_sets:[c]} as MimiConversation
  const snapshot={...before,change_sets:[{...c,state:'stale',confirmation_preflight:{status:'blocked' as const,reason:'change_set_stale'}}]}
  const key=['mimi','conversation',intent.conversationId]
  const store=new Map<string,string>();vi.stubGlobal('sessionStorage',{setItem:(k:string,v:string)=>store.set(k,v),getItem:(k:string)=>store.get(k),removeItem:(k:string)=>store.delete(k)})
  saveMimiIntent(intent);client.setQueryData(key,before);client.setQueryData(['mimi','current'],before)
  let finishRead!:(value:MimiConversation)=>void
  const inflight=client.fetchQuery({queryKey:key,queryFn:()=>new Promise<MimiConversation>((resolve)=>{finishRead=resolve})}).catch(()=>null)
  expect(await publishAuthoritativeMimiRefusal(client,intent,snapshot)).toBe(true)
  expect(readMimiIntent(intent.conversationId,[c])?.key).toBe('same-key') // caller has not released yet
  expect(client.getQueryData(key)).toEqual(snapshot)
  expect(client.getQueryData(['mimi','current'])).toEqual(snapshot)
  expect(collectionConfirmationNotice(client.getQueryData<MimiConversation>(key)!.change_sets[0])).not.toBeNull()
  clearMimiIntent(intent.conversationId);finishRead(before);await inflight
  expect(client.getQueryData(key)).toEqual(snapshot)
  expect(readMimiIntent(intent.conversationId,[c])).toBeNull();client.clear()
})

it('never overwrites another current conversation and refuses mismatched/absent/nonterminal snapshots', async () => {
  const client=new QueryClient({defaultOptions:{queries:{gcTime:0}}})
  const c={id:'c',digest:'d',nonce:'n',state:'pending',confirmation_preflight:{status:'eligible',reason:null}} as MimiChangeSet
  const intent={conversationId:'owner-conv',changeSet:c,choice:'confirm' as const,key:'same-key'}
  const before={id:'owner-conv',change_sets:[c]} as MimiConversation
  const other={id:'other-conv',change_sets:[]} as unknown as MimiConversation
  const key=['mimi','conversation','owner-conv'];client.setQueryData(key,before);client.setQueryData(['mimi','current'],other)
  for(const bad of [{...before,id:'other-conv'}, {...before,change_sets:[]},before,{...before,change_sets:[{...c,state:'stale',nonce:'wrong'}]},{...before,change_sets:[{...c,state:'stale',digest:'wrong'}]}]) {
    expect(await publishAuthoritativeMimiRefusal(client,intent,bad)).toBe(false)
    expect(client.getQueryData(key)).toEqual(before)
  }
  const good={...before,change_sets:[{...c,state:'stale',confirmation_preflight:{status:'blocked' as const,reason:'change_set_stale'}}]}
  expect(await publishAuthoritativeMimiRefusal(client,intent,good)).toBe(true)
  expect(client.getQueryData(['mimi','current'])).toEqual(other);client.clear()
})

it('cancels an empty current cache inflight read before releasing a matching refusal intent', async () => {
  const client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}})
  const c={id:'c',digest:'d',nonce:'n',state:'pending',confirmation_preflight:{status:'eligible',reason:null}} as MimiChangeSet
  const intent={conversationId:'owner-conv',changeSet:c,choice:'confirm' as const,key:'same-key'}
  const before={id:intent.conversationId,change_sets:[c]} as MimiConversation
  const snapshot={...before,change_sets:[{...c,state:'stale',confirmation_preflight:{status:'blocked' as const,reason:'change_set_stale'}}]}
  const key=['mimi','conversation',intent.conversationId]
  const currentKey=['mimi','current']
  const store=new Map<string,string>();vi.stubGlobal('sessionStorage',{setItem:(k:string,v:string)=>store.set(k,v),getItem:(k:string)=>store.get(k),removeItem:(k:string)=>store.delete(k)})
  saveMimiIntent(intent)
  let finishRead!:(value:MimiConversation)=>void
  const inflight=client.fetchQuery({queryKey:currentKey,queryFn:()=>new Promise<MimiConversation>((resolve)=>{finishRead=resolve})}).catch(()=>null)
  expect(client.getQueryData(currentKey)).toBeUndefined()
  expect(client.getQueryState(currentKey)?.fetchStatus).toBe('fetching')
  expect(await publishAuthoritativeMimiRefusal(client,intent,snapshot)).toBe(true)
  expect(client.getQueryState(currentKey)?.fetchStatus).toBe('idle')
  expect(client.getQueryData(key)).toEqual(snapshot)
  expect(collectionConfirmationNotice(snapshot.change_sets[0])).not.toBeNull()
  expect(readMimiIntent(intent.conversationId,[c])?.key).toBe('same-key')
  clearMimiIntent(intent.conversationId)
  finishRead(before);await inflight
  expect(client.getQueryData(currentKey)).toBeUndefined()
  expect(client.getQueryData(key)).toEqual(snapshot)
  expect(readMimiIntent(intent.conversationId,[c])).toBeNull();client.clear()
})
