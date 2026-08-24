import type { ApiError } from '@/api'

export type CalendarSource = {
  id: string
  name: string
  kind: string
  color: string | null
  is_visible: boolean
  event_count: number
  created_at: string | null
  updated_at: string | null
}

export type CalendarEvent = {
  id: string
  source_id: string
  title: string
  starts_at: string
  ends_at: string
  all_day: boolean
  location: string | null
  description_md: string | null
  created_at: string | null
  updated_at: string | null
}

export type ImportReport = {
  parsed: number
  inserted: number
  removed: number
  duplicates: number
  skipped: string[]
}

export const VIETNAM_TIME_ZONE = 'Asia/Ho_Chi_Minh'
export const SOURCE_COLORS: Record<string, string> = {
  rose: 'var(--rose-500)',
  amber: 'var(--warn)',
  emerald: 'var(--ok)',
  sky: 'var(--primary)',
  violet: 'var(--rose-700)',
  slate: 'var(--n-500)',
}

export const SOURCE_COLOR_KEYS = Object.keys(SOURCE_COLORS)

export function sourceColorToken(color: string | null): string {
  return SOURCE_COLORS[color ?? 'slate'] ?? SOURCE_COLORS.slate
}

function dateParts(value: Date): Record<string, string> {
  return Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', {
      timeZone: VIETNAM_TIME_ZONE,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
      .formatToParts(value)
      .filter(({ type }) => type !== 'literal')
      .map(({ type, value: part }) => [type, part]),
  )
}

export function todayInVietnam(): string {
  const parts = dateParts(new Date())
  return `${parts.year}-${parts.month}-${parts.day}`
}

export function addVietnamDays(day: string, days: number): string {
  const date = new Date(`${day}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

export function vietnamMidnight(day: string): string {
  return `${day}T00:00:00+07:00`
}

export function rangeQuery(startDay: string): { from: string; to: string } {
  return { from: vietnamMidnight(startDay), to: vietnamMidnight(addVietnamDays(startDay, 30)) }
}

export function formatVietnamDate(value: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: VIETNAM_TIME_ZONE,
    weekday: 'long',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(value))
}

export function formatVietnamTime(event: Pick<CalendarEvent, 'starts_at' | 'ends_at' | 'all_day'>): string {
  if (event.all_day) return 'Cả ngày'
  const formatter = new Intl.DateTimeFormat('vi-VN', {
    timeZone: VIETNAM_TIME_ZONE,
    hour: '2-digit',
    minute: '2-digit',
  })
  return `${formatter.format(new Date(event.starts_at))}–${formatter.format(new Date(event.ends_at))}`
}

export function eventDateKey(value: string): string {
  return todayInVietnamFromDate(new Date(value))
}

function todayInVietnamFromDate(value: Date): string {
  const parts = dateParts(value)
  return `${parts.year}-${parts.month}-${parts.day}`
}

export function toVietnamDateTimeInput(value: string | null): string {
  if (!value) return ''
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: VIETNAM_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  })
    .formatToParts(new Date(value))
    .filter(({ type }) => type !== 'literal')
    .reduce<Record<string, string>>((result, part) => {
      result[part.type] = part.value
      return result
    }, {})
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`
}

export function vietnamInputToIso(value: string): string {
  const normalized = value.length === 16 ? `${value}:00` : value
  const guess = new Date(`${normalized}Z`)
  const zonePart = new Intl.DateTimeFormat('en-US', {
    timeZone: VIETNAM_TIME_ZONE,
    timeZoneName: 'longOffset',
  }).formatToParts(guess).find(({ type }) => type === 'timeZoneName')?.value
  const offset = zonePart?.match(/^GMT([+-]\d{2}:\d{2})$/)?.[1]
  if (!offset || Number.isNaN(guess.getTime())) {
    throw new Error('Vietnam civil datetime is invalid')
  }
  return `${normalized}${offset}`
}

export function allDayVietnamRange(day: string): { startsAt: string; endsAt: string } {
  return {
    startsAt: `${day}T00:00`,
    endsAt: `${addVietnamDays(day, 1)}T00:00`,
  }
}

export function groupEvents(events: CalendarEvent[]): Array<[string, CalendarEvent[]]> {
  const groups = new Map<string, CalendarEvent[]>()
  for (const event of events) {
    const key = eventDateKey(event.starts_at)
    const current = groups.get(key) ?? []
    current.push(event)
    groups.set(key, current)
  }
  return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right))
}

export function importConflict(error: unknown): { existingSourceId: string; message: string } | null {
  const responseBody = (error as ApiError | undefined)?.body
  if (!responseBody || typeof responseBody !== 'object' || !('detail' in responseBody)) return null
  const detail = (responseBody as { detail?: unknown }).detail
  if (!detail || typeof detail !== 'object') return null
  const body = detail as { code?: unknown; existing_source_id?: unknown; message?: unknown }
  if (body.code !== 'source_name_taken' || typeof body.existing_source_id !== 'string') return null
  return {
    existingSourceId: body.existing_source_id,
    message: typeof body.message === 'string' ? body.message : 'Đã có nguồn cùng tên.',
  }
}

export function importErrorMessage(error: unknown): string {
  const responseBody = (error as ApiError | undefined)?.body
  const detail =
    responseBody && typeof responseBody === 'object' && 'detail' in responseBody
      ? (responseBody as { detail?: unknown }).detail
      : undefined
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const message = (detail as { message?: unknown }).message
    if (typeof message === 'string') return message
  }
  if (error instanceof Error) return error.message
  return 'Không thể nhập lịch. Kiểm tra file rồi thử lại.'
}

export function eventDialogErrorMessage(eventError: string | null, mutationError: unknown): string | null {
  if (eventError) return eventError
  return mutationError ? importErrorMessage(mutationError) : null
}
