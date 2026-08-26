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

export type FutureReflection = {
  id: string
  time: string
  text: string
}

export type ParsedNoteBody = {
  baseText: string
  reflections: FutureReflection[]
}

const REFLECTION_HEADER_REGEX = /^>\s*💬\s*\*\*Lời nhắn từ tương lai\*\*\s*\(([^)]+)\):\s*$/m

export function parseNoteBody(bodyMd: string | null | undefined): ParsedNoteBody {
  if (!bodyMd) return { baseText: '', reflections: [] }
  const trimmed = bodyMd.trim()
  if (!trimmed) return { baseText: '', reflections: [] }

  const parts = trimmed.split(/\n\s*---\s*\n/)
  const reflections: FutureReflection[] = []
  const nonReflectionParts: string[] = []

  for (const part of parts) {
    const trimmedPart = part.trim()
    const match = trimmedPart.match(REFLECTION_HEADER_REGEX)
    if (match) {
      const time = match[1]
      const lines = trimmedPart.split('\n')
      const headerIndex = lines.findIndex((l) => REFLECTION_HEADER_REGEX.test(l.trim()))
      const textLines = lines.slice(headerIndex + 1).map((l) => l.replace(/^>\s?/, ''))
      const text = textLines.join('\n').trim()
      reflections.push({
        id: `reflection-${reflections.length}`,
        time,
        text,
      })
    } else {
      if (trimmedPart.includes('Lời nhắn từ tương lai')) {
        const lines = trimmedPart.split('\n')
        const currentBaseLines: string[] = []
        let currentReflTime: string | null = null
        let currentReflLines: string[] = []

        for (const line of lines) {
          const m = line.trim().match(REFLECTION_HEADER_REGEX)
          if (m) {
            if (currentReflTime !== null) {
              reflections.push({
                id: `reflection-${reflections.length}`,
                time: currentReflTime,
                text: currentReflLines.map((l) => l.replace(/^>\s?/, '')).join('\n').trim(),
              })
              currentReflLines = []
            }
            currentReflTime = m[1]
          } else if (currentReflTime !== null) {
            currentReflLines.push(line)
          } else {
            currentBaseLines.push(line)
          }
        }
        if (currentReflTime !== null) {
          reflections.push({
            id: `reflection-${reflections.length}`,
            time: currentReflTime,
            text: currentReflLines.map((l) => l.replace(/^>\s?/, '')).join('\n').trim(),
          })
        }
        if (currentBaseLines.length > 0) {
          const b = currentBaseLines.join('\n').trim()
          if (b) nonReflectionParts.push(b)
        }
      } else {
        nonReflectionParts.push(trimmedPart)
      }
    }
  }

  return {
    baseText: nonReflectionParts.join('\n\n---\n\n').trim(),
    reflections,
  }
}

export function serializeNoteBody(
  baseText: string,
  reflections: Array<{ time: string; text: string }>,
): string {
  const blocks: string[] = []
  const cleanBase = baseText.trim()
  if (cleanBase) blocks.push(cleanBase)

  for (const r of reflections) {
    const cleanText = r.text.trim()
    if (!cleanText) continue
    const quoted = cleanText.replace(/\n/g, '\n> ')
    blocks.push(`> 💬 **Lời nhắn từ tương lai** (${r.time}):\n> ${quoted}`)
  }

  return blocks.join('\n\n---\n\n')
}

export function updateFutureReflection(
  currentBodyMd: string | null | undefined,
  reflectionIndex: number,
  newText: string,
): string {
  const parsed = parseNoteBody(currentBodyMd)
  if (reflectionIndex < 0 || reflectionIndex >= parsed.reflections.length) {
    return currentBodyMd?.trim() || ''
  }
  const updatedReflections = [...parsed.reflections]
  updatedReflections[reflectionIndex] = {
    ...updatedReflections[reflectionIndex],
    text: newText.trim(),
  }
  return serializeNoteBody(parsed.baseText, updatedReflections)
}

export function deleteFutureReflection(
  currentBodyMd: string | null | undefined,
  reflectionIndex: number,
): string {
  const parsed = parseNoteBody(currentBodyMd)
  if (reflectionIndex < 0 || reflectionIndex >= parsed.reflections.length) {
    return currentBodyMd?.trim() || ''
  }
  const updatedReflections = parsed.reflections.filter((_, idx) => idx !== reflectionIndex)
  return serializeNoteBody(parsed.baseText, updatedReflections)
}
