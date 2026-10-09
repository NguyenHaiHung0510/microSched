import { describe, expect, it } from 'vitest'
import { collectionConfirmable, collectionConfirmationNotice, collectionCounts, collectionFieldDiff, collectionPage } from './mimi-collection'
import type { MimiChangeSet, MimiCollectionPlan, MimiSelection } from './mimi-api'
describe('frozen collection review', () => {
  const plan: MimiCollectionPlan = { schema_version: 'mimi.task-collection.v1', selection_id: 'selection', entries: Array.from({ length: 200 }, (_, i) => ({ id: `id-${i}`, command: { action: 'edit', expected_collection_version: 7, fields: { priority: 'p1' }, children: [], reminder: { action: 'keep' } }, before: { fields: { title: `Task ${i}`, body_md: 'ế'.repeat(12000), priority: null }, children: [] }, after: { fields: { title: `Task ${i}`, body_md: 'ế'.repeat(12000), priority: 'p1' }, children: [] }, reminder_effect: { action: 'keep' } })) }
  const selection = { members: [...plan.entries.map((e) => ({ id: e.id, classification: 'included' })), { id: 'incidental', classification: 'excluded' }, { id: 'uncertain', classification: 'uncertain' }] } as MimiSelection
  it('200 targets stay frozen while search, filters and page transitions show at most20', () => {
    const frozen = JSON.stringify(plan)
    expect(collectionPage(plan, '', 'all', selection, 0).entries).toHaveLength(20)
    expect(collectionPage(plan, '', 'all', selection, 9).entries[19].id).toBe('id-199')
    expect(collectionPage(plan, 'id-199', 'all', selection, 9)).toMatchObject({ visibleCount: 1, currentPage: 0 })
    expect(collectionPage(plan, '', 'excluded', selection, 0).entries).toHaveLength(0)
    expect(collectionCounts(plan, selection)).toEqual({ affected: 200, included: 200, excluded: 1, uncertain: 1 })
    expect(JSON.stringify(plan)).toBe(frozen)
  })
  it('field diffs retain the entire body rather than a truncated approval value', () => {
    const entry = structuredClone(plan.entries[0]); entry.after.fields.body_md = '🏃'.repeat(12000)
    const body = collectionFieldDiff(entry).find((diff) => diff.key === 'body_md')!
    expect(body.before).toBe('ế'.repeat(12000)); expect(body.after).toBe('🏃'.repeat(12000))
  })
  it('named subsets remain confirmable with honest query omissions, all-scope unresolved or mismatched IDs never do', () => {
    const bound = { ...selection, selection_id: 'selection', explicitly_named_subset: true, query_complete: false, semantic_complete: false }
    expect(collectionConfirmable(plan, bound)).toBe(true)
    expect(collectionConfirmable(plan, { ...bound, explicitly_named_subset: false })).toBe(false)
    expect(collectionConfirmable(plan, { ...bound, selection_id: 'other' })).toBe(false)
    expect(collectionConfirmable(plan, { ...bound, members: bound.members.slice(1) })).toBe(false)
  })

})

describe('server-owned collection preflight', () => {
  it('keeps a stale/expired/missing preflight disabled without modifying frozen bindings', () => {
    const change = { id:'c',digest:'d',nonce:'n',expires_at:'2026-10-10',confirmation_preflight:{status:'blocked',reason:'change_set_frontier_stale'} } as MimiChangeSet
    const frozen = JSON.stringify(change)
    expect(collectionConfirmationNotice(change)).toContain('hội thoại đã thay đổi')
    expect(JSON.stringify(change)).toBe(frozen)
    expect(collectionConfirmationNotice({...change,confirmation_preflight:{status:'blocked',reason:'change_set_expired'}})).toContain('hết hạn')
    expect(collectionConfirmationNotice({...change,confirmation_preflight:undefined})).toContain('Chưa có trạng thái')
    expect(collectionConfirmationNotice({...change,confirmation_preflight:{status:'eligible',reason:null}})).toBeNull()
  })
})
