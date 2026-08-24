/** Pure note-form state rules kept testable without a browser runtime. */

export type NoteItem = {
  id: string
  content: string
  is_completed: boolean
  position: number
  created_at?: string | null
  updated_at?: string | null
}

export type Note = {
  id: string
  title: string | null
  body_md: string | null
  is_private: boolean
  pinned: boolean
  items: NoteItem[]
  created_at: string | null
  updated_at: string | null
}

export type NoteFormState = {
  title: string
  body: string
  isPrivate: boolean
  pinned?: boolean
}

export type NoteWritePayload = {
  title: string | null
  body_md: string | null
  is_private: boolean
  pinned?: boolean
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
    ...(state.pinned !== undefined ? { pinned: state.pinned } : {}),
  }
}

export function canSubmitNote(state: NoteFormState, pending: boolean): boolean {
  return (state.title.trim().length > 0 || state.body.trim().length > 0) && !pending
}

/** Format note creation/update time in Vietnam timezone (HH:mm · DD/MM/YYYY) */
export function formatNoteTime(isoString: string | null | undefined): string {
  if (!isoString) return ''
  const d = new Date(isoString)
  if (isNaN(d.getTime())) return ''
  const formatter = new Intl.DateTimeFormat('vi-VN', {
    timeZone: 'Asia/Ho_Chi_Minh',
    hour: '2-digit',
    minute: '2-digit',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hourCycle: 'h23',
  })
  const parts = formatter.formatToParts(d)
  const map: Record<string, string> = {}
  for (const part of parts) {
    map[part.type] = part.value
  }
  return `${map.hour || '00'}:${map.minute || '00'} · ${map.day}/${map.month}/${map.year}`
}

/** Append a "Lời nhắn từ tương lai" reflection to the note body */
export function appendFutureReflection(
  currentBodyMd: string | null | undefined,
  reflectionText: string,
  nowIso: string = new Date().toISOString(),
): string {
  const trimmedReflection = reflectionText.trim()
  if (!trimmedReflection) return currentBodyMd?.trim() || ''
  const timeFormatted = formatNoteTime(nowIso)
  const reflectionBlock = `> 💬 **Lời nhắn từ tương lai** (${timeFormatted}):\n> ${trimmedReflection.replace(/\n/g, '\n> ')}`
  const base = currentBodyMd?.trim() || ''
  if (!base) {
    return reflectionBlock
  }
  return `${base}\n\n---\n${reflectionBlock}`
}
