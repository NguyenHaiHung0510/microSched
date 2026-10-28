import { describe, expect, it } from 'vitest'
import { hasUnsentFeedback, safeAutomaticUpdate } from './pwa-update'

const clean = {dirty: false, composing: false, mutating: false, admitting: 0, storageReady: true, sending: false}
describe('automatic update boundary', () => {
  it('allows an idle verified app while a durable unsent queue may remain', () => { expect(safeAutomaticUpdate(clean)).toBe(true) })
  it.each([
    {dirty: true}, {composing: true}, {mutating: true}, {admitting: 1}, {storageReady: false}, {sending: true},
  ])('defers without clearing user state: %j', change => { expect(safeAutomaticUpdate({...clean, ...change})).toBe(false) })
})

describe('feedback owner after ACK', () => {
  it('keeps an unsent reason-only draft', () => expect(hasUnsentFeedback('', '', ['Khác'], false)).toBe(true))
  it('allows update after ACK with retained reason selection', () => expect(hasUnsentFeedback('', '', ['Khác'], true)).toBe(false))
  it('keeps newer prose despite an earlier ACK', () => expect(hasUnsentFeedback('bản mới', '', ['Khác'], true)).toBe(true))
})
