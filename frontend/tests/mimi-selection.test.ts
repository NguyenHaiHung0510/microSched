import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { readMimiComposerDraft, setMimiComposerDraft, selectMimiConversation, readMimiSelection, selectCreatedMimiConversation } from '../src/mimi-selection'
import type { MimiConversationSummary } from '../src/mimi-api'
import { mergeMimiConversationPages } from '../src/mimi-conversation-list'

const first = '01800000-0000-7000-8000-000000000001'
const second = '01800000-0000-7000-8000-000000000002'
beforeEach(() => {
  const items = new Map<string, string>()
  const events = new EventTarget()
  vi.stubGlobal('window', { sessionStorage: {
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => items.set(key, value),
    removeItem: (key: string) => items.delete(key),
  }, dispatchEvent: (event: Event) => events.dispatchEvent(event) })
  selectMimiConversation(null)
})
afterEach(() => vi.unstubAllGlobals())

describe('conversation continuity', () => {
  it('keeps independent unsent drafts across selection changes and clears them at logout', () => {
    selectMimiConversation(first)
    setMimiComposerDraft(first, 'Đoạn đang gõ, chưa gửi và chưa được model thấy')
    selectMimiConversation(second)
    expect(readMimiComposerDraft(second)).toBe('')
    setMimiComposerDraft(second, 'Một việc khác')
    selectMimiConversation(first)
    expect(readMimiSelection()).toBe(first)
    expect(readMimiComposerDraft(first)).toBe('Đoạn đang gõ, chưa gửi và chưa được model thấy')
    expect(readMimiComposerDraft(second)).toBe('Một việc khác')
    selectMimiConversation(null)
    expect(readMimiComposerDraft(first)).toBe('')
    expect(readMimiComposerDraft(second)).toBe('')
    expect(readMimiSelection()).toBeNull()
  })
  it('exposes a newly created conversation to both dock and workspace list caches before selection', () => {
    const client = new QueryClient()
    const created: MimiConversationSummary = { id: first, sensitivity:'standard', title:'Hội thoại mới', title_source:'auto', title_locked:false, generation:1, metadata_version:1, archived_at:null, updated_at:'2026-10-02T11:00:00Z', latest_run_state:null }
    client.setQueryData(['mimi', 'conversations', 'paged', 'all'], {pages:[{items:[],next_cursor:'page2'}],pageParams:[null]})
    selectCreatedMimiConversation(client, created)
    expect(client.getQueryData(['mimi', 'conversations', 'active'])).toEqual({items:[created],next_cursor:null})
    expect(client.getQueryData(['mimi', 'conversations', 'all'])).toEqual({items:[created],next_cursor:null})
    expect(readMimiSelection()).toBe(first)
    expect(client.getQueryData(['mimi', 'conversations', 'paged', 'all'])).toEqual({pages:[{items:[created],next_cursor:'page2'}],pageParams:[null]})
    client.clear()
  })
  it('keeps older conversations beyond page50 and avoids duplicate IDs after a list refresh', () => {
    const items = Array.from({length:51},(_,index) => ({id:String(index)} as MimiConversationSummary))
    const merged = mergeMimiConversationPages([{items:items.slice(0,50),next_cursor:'opaque'},{items:[items[49],items[50]],next_cursor:null}])
    expect(merged).toHaveLength(51)
    expect(merged[50].id).toBe('50')
  })
})
