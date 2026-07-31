import { describe, expect, it } from 'vitest'

import { canSubmitNote, notePayload, type NoteFormState } from '@/note-ui'

function state(overrides: Partial<NoteFormState> = {}): NoteFormState {
  return {
    title: '',
    body: '',
    isPrivate: false,
    ...overrides,
  }
}

describe('note form rules', () => {
  it('allows a body-only note and maps its nullable title', () => {
    const bodyOnly = state({ body: '  Nội dung chính  ' })

    expect(canSubmitNote(bodyOnly, false)).toBe(true)
    expect(notePayload(bodyOnly)).toEqual({
      title: null,
      body_md: 'Nội dung chính',
      is_private: false,
    })
  })

  it('rejects a completely blank or pending form', () => {
    expect(canSubmitNote(state({ title: '   ', body: '\n  ' }), false)).toBe(false)
    expect(canSubmitNote(state({ title: 'Có tiêu đề' }), true)).toBe(false)
  })

  it('keeps title and privacy in the write payload', () => {
    expect(notePayload(state({ title: '  Ghi chú  ', isPrivate: true }))).toEqual({
      title: 'Ghi chú',
      body_md: null,
      is_private: true,
    })
  })
})
