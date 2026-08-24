import { describe, expect, it } from 'vitest'

import {
  appendFutureReflection,
  canSubmitNote,
  formatNoteTime,
  notePayload,
  type NoteFormState,
} from '@/note-ui'

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

  it('includes pinned when specified', () => {
    expect(notePayload(state({ title: 'Ghim', pinned: true }))).toEqual({
      title: 'Ghim',
      body_md: null,
      is_private: false,
      pinned: true,
    })
  })
})

describe('note time formatting', () => {
  it('formats Vietnam timezone timestamp correctly', () => {
    const formatted = formatNoteTime('2026-08-24T07:30:00.000Z')
    expect(formatted).toBe('14:30 · 24/08/2026')
  })

  it('handles null/invalid timestamp gracefully', () => {
    expect(formatNoteTime(null)).toBe('')
    expect(formatNoteTime(undefined)).toBe('')
    expect(formatNoteTime('invalid-date')).toBe('')
  })
})

describe('future reflection formatting', () => {
  it('appends reflection with header and quote format', () => {
    const initialBody = 'Cần mua Gemini Pro để test harness.'
    const reflection = 'Đã có cả GPT Plus và OpenRouter cùng hoạt động!'
    const nowIso = '2026-09-24T07:30:00.000Z'

    const result = appendFutureReflection(initialBody, reflection, nowIso)
    expect(result).toContain('Cần mua Gemini Pro để test harness.')
    expect(result).toContain('---')
    expect(result).toContain('Lời nhắn từ tương lai')
    expect(result).toContain('Đã có cả GPT Plus và OpenRouter cùng hoạt động!')
  })

  it('handles multiline reflection and empty base body', () => {
    const reflection = 'Dòng 1\nDòng 2'
    const nowIso = '2026-09-24T07:30:00.000Z'

    const result = appendFutureReflection(null, reflection, nowIso)
    expect(result).toContain('Dòng 1')
    expect(result).toContain('Dòng 2')
  })
})
