/** Pure note-form state rules kept testable without a browser runtime. */

export type NoteFormState = {
  title: string
  body: string
  isPrivate: boolean
}

export type NoteWritePayload = {
  title: string | null
  body_md: string | null
  is_private: boolean
}

export type NotePayload = NoteWritePayload & {
  id: string
}

export const noteInvalidationKey = ['notes'] as const
export const noteQueryKey = ['notes'] as const

export function notePayload(state: NoteFormState): NoteWritePayload {
  return {
    title: state.title.trim() || null,
    body_md: state.body.trim() || null,
    is_private: state.isPrivate,
  }
}

export function canSubmitNote(state: NoteFormState, pending: boolean): boolean {
  return (state.title.trim().length > 0 || state.body.trim().length > 0) && !pending
}
