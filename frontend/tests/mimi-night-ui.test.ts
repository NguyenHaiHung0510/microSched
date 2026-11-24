import { afterEach, expect, test, vi } from 'vitest'
import { activeMimiPreview, blockedNewMimiPreview, matchesMimiPreview } from '../src/mimi-active-preview'
import { acceptsMimiShortcut } from '../src/mimi-quick-access'
import { hasUnsentRetainedMimiFeedback } from '../src/mimi-feedback-state'
import { decideMimiChangeSet, type MimiChangeSet, type MimiConversation } from '../src/mimi-api'

afterEach(() => vi.unstubAllGlobals())
const change: MimiChangeSet = {
  id: 'synthetic-a', digest: 'a'.repeat(64), nonce: 'nonce-a', state: 'pending', run_id: 'run-a',
  expires_at: '2099-01-01T00:00:00Z', policy_version: 'synthetic', operation: {
    operation_id: 'op-a', tool: 'task.create.v1', args: { id: 'task-a', title: 'A', body_md: null,
      status: 'open', priority: null, due_precision: 'none', due_on: null, due_at: null, is_private: false, items: [] },
  },
}
const conversation: MimiConversation = { id: 'synthetic-conversation', sensitivity: 'standard', generation: 1,
  messages: [], runs: [], change_sets: [change], receipts: [], events: [], feedback: [] }
const binding = { conversationId: conversation.id, id: change.id, digest: change.digest, nonce: change.nonce }

test('one-active preview ignores terminal array ordering and fails closed on ambiguous active identities', () => {
  const stale = { ...change, id: 'old', state: 'stale' }
  expect(activeMimiPreview([change, stale])).toBe(change)
  expect(activeMimiPreview([stale, change])).toBe(change)
  expect(activeMimiPreview([change, { ...change, id: 'b' }])).toBeUndefined()
  expect(activeMimiPreview([{ ...change, state: 'rejected' }])).toBeUndefined()
})

test('retained negative draft/unknown intent prevents a PWA reload after the dock unmounts', () => {
  expect(hasUnsentRetainedMimiFeedback(undefined)).toBe(false)
  for (const fields of [{ draft: 'Chưa lưu' }, { expected: 'Mong đợi' }, { intent: { clientId: 'same-key' } }, { reasons: ['Khác'] }]) {
    expect(hasUnsentRetainedMimiFeedback(fields)).toBe(true)
  }
  expect(hasUnsentRetainedMimiFeedback({ reasons: ['Khác'], acknowledgment: { targetKey: 'turn:m' } })).toBe(false)
  expect(hasUnsentRetainedMimiFeedback({ draft: 'Bản sửa mới', acknowledgment: { targetKey: 'turn:m' } })).toBe(true)
})

test('revision identity is exact across conversation, digest, nonce and pending state', () => {
  expect(matchesMimiPreview(conversation, change, binding)).toBe(true)
  for (const altered of [{ ...binding, conversationId: 'other' }, { ...binding, id: 'other' },
    { ...binding, digest: 'other' }, { ...binding, nonce: 'other' }]) {
    expect(matchesMimiPreview(conversation, change, altered)).toBe(false)
  }
  expect(matchesMimiPreview(conversation, { ...change, state: 'stale' }, binding)).toBe(false)
  expect(blockedNewMimiPreview({ ...conversation, runs: [{ error_code: 'pending_preview_requires_decision' } as MimiConversation['runs'][number]] })).toBe(true)
  expect(blockedNewMimiPreview(conversation)).toBe(false)
})

test.each(['wrong-id', 'wrong-digest', 'wrong-operation', 'wrong-choice'])('decision ACK %s retains uncertainty instead of accepting another frozen write', async mismatch => {
  const receipt = { change_set_id: change.id, digest: change.digest, operation_id: change.operation.operation_id, executed_at: '2026-10-29T00:00:00Z' }
  if (mismatch === 'wrong-id') receipt.change_set_id = 'other'
  if (mismatch === 'wrong-digest') receipt.digest = 'other'
  if (mismatch === 'wrong-operation') receipt.operation_id = 'other'
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(receipt), { status: 200 })))
  await expect(decideMimiChangeSet(change, mismatch === 'wrong-choice' ? 'reject' : 'confirm', 'same-key'))
    .rejects.toThrow('acknowledgment does not match')
})

test('Alt+A respects editing, IME, AltGr, browser modifiers and modal layers', () => {
  class Target { constructor(public editing = false) {} closest() { return this.editing ? this : null } }
  vi.stubGlobal('Element', Target)
  const event = { altKey: true, code: 'KeyA', getModifierState: () => false, target: new Target() } as unknown as KeyboardEvent
  const doc = { activeElement: null, querySelector: () => null } as unknown as Document
  expect(acceptsMimiShortcut(event, doc)).toBe(true)
  for (const override of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { repeat: true },
    { isComposing: true }, { keyCode: 229 }, { defaultPrevented: true }, { altKey: false },
    { code: 'KeyB' }, { getModifierState: () => true }, { target: new Target(true) }]) {
    expect(acceptsMimiShortcut({ ...event, ...override } as unknown as KeyboardEvent, doc)).toBe(false)
  }
  expect(acceptsMimiShortcut(event, { ...doc, querySelector: () => ({}) } as unknown as Document)).toBe(false)
})
