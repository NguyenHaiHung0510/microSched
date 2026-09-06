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

export type NoteSortMode = 'alphabet' | 'created' | 'updated'

export const NOTE_PAGE_LIMIT = 100
export const MAX_NOTE_PAGES = 20

export class NotePageLimitError extends Error {
  constructor(message = 'Không tải đủ ghi chú để sắp xếp. Thử lại.') {
    super(message)
    this.name = 'NotePageLimitError'
  }
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
      if (headerIndex > 0) {
        const baseBefore = lines.slice(0, headerIndex).join('\n').trim()
        if (baseBefore) nonReflectionParts.push(baseBefore)
      }
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

export function sortNotes(notes: Note[], mode: NoteSortMode = 'alphabet'): Note[] {
  const collator = new Intl.Collator('vi-VN', { sensitivity: 'base', numeric: true })

  return [...notes].sort((a, b) => {
    // 1. Primary partition: pinned always first
    if (a.pinned !== b.pinned) {
      return a.pinned ? -1 : 1
    }

    const labelA = a.title || 'Không tiêu đề'
    const labelB = b.title || 'Không tiêu đề'

    // 2. Mode comparator
    if (mode === 'alphabet') {
      const cmp = collator.compare(labelA, labelB)
      if (cmp !== 0) return cmp
    } else if (mode === 'created') {
      const dateA = a.created_at ?? ''
      const dateB = b.created_at ?? ''
      const cmp = dateB.localeCompare(dateA)
      if (cmp !== 0) return cmp
    } else if (mode === 'updated') {
      const dateA = a.updated_at ?? a.created_at ?? ''
      const dateB = b.updated_at ?? b.created_at ?? ''
      const cmp = dateB.localeCompare(dateA)
      if (cmp !== 0) return cmp
    }

    // 3. Tie-breakers: label -> created_at -> id
    const labelCmp = collator.compare(labelA, labelB)
    if (labelCmp !== 0) return labelCmp

    const createdCmp = (b.created_at ?? '').localeCompare(a.created_at ?? '')
    if (createdCmp !== 0) return createdCmp

    return a.id.localeCompare(b.id)
  })
}

export async function fetchAllNotes(
  fetchPage: (limit: number, offset: number) => Promise<{ items: Note[] }>,
): Promise<Note[]> {
  const allNotes: Note[] = []
  const seenIds = new Set<string>()
  const seenFingerprints = new Set<string>()
  let offset = 0
  let pageCount = 0

  while (pageCount < MAX_NOTE_PAGES) {
    const res = await fetchPage(NOTE_PAGE_LIMIT, offset)
    const items = res?.items ?? []

    if (items.length === 0) {
      break
    }

   // Oracle: Page with items.length > 100 must fail visible
   if (items.length > NOTE_PAGE_LIMIT) {
     throw new NotePageLimitError()
   }

    // 2. Fingerprint ordered raw IDs
    const fingerprint = items.map((n) => n.id).join(',')
   if (seenFingerprints.has(fingerprint)) {
     throw new NotePageLimitError()
   }
   seenFingerprints.add(fingerprint)

  const prevUniqueCount = seenIds.size

  // 3. De-duplicate across pages by ID: keep new unique notes
  for (const note of items) {
    if (seenIds.has(note.id)) {
       continue
    }
    seenIds.add(note.id)
    allNotes.push(note)
  }

   // If page returned items but unique count did not increase (offset not progressing / full repeat), fail visible
    if (seenIds.size === prevUniqueCount) {
      throw new NotePageLimitError()
    }

    // Oracle: Unique global count cannot exceed 2000 before probe
    if (seenIds.size > MAX_NOTE_PAGES * NOTE_PAGE_LIMIT) {
      throw new NotePageLimitError()
    }

    pageCount++

    if (items.length < NOTE_PAGE_LIMIT) {
      break
    }

    offset += items.length

    // 4. After 20 full pages, fetch probe offset 2000
    if (pageCount === MAX_NOTE_PAGES) {
      const probe = await fetchPage(NOTE_PAGE_LIMIT, offset)
      const probeItems = probe?.items ?? []
      if (probeItems.length > 0) {
        throw new NotePageLimitError()
      }
      break
    }
  }

  return allNotes
}
