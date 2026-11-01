import { afterEach, expect, test, vi } from 'vitest'
import { acceptsMimiShortcut } from '../src/mimi-quick-access'

afterEach(() => vi.unstubAllGlobals())

test('Alt+A accepts only an unclaimed non-editing application key', () => {
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
  expect(acceptsMimiShortcut(event, { ...doc, activeElement: new Target(true) } as unknown as Document)).toBe(true)
  expect(acceptsMimiShortcut({ ...event, target: null } as unknown as KeyboardEvent,
    { ...doc, activeElement: new Target(true) } as unknown as Document)).toBe(false)
  expect(acceptsMimiShortcut(event, { ...doc, querySelector: () => ({}) } as unknown as Document)).toBe(false)
})
