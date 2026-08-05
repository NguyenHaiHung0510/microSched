/** Pure tracker-slice rules (sort, money, time, backdate) + the single mutation seam.
 *
 * The mutation seam is the 017 door: every write of the tracker screen — group /
 * tracker / entry CRUD, one-tap capture and undo — goes through the mutations this
 * module returns, never through a bare `apiRequest` call inside a component. 017
 * will wrap exactly this one place with its offline outbox.
 */

import { useMutation } from '@tanstack/react-query'

import { apiRequest } from '@/api'
import { VIETNAM_TIME_ZONE, vietnamInputToIso } from '@/calendar-ui'
import { uuidv7 } from '@/lib/uuidv7'

export type TrackerKind = 'health' | 'finance'
export type TrackerDirection = 'in' | 'out'
export type TrackerInputMode = 'event' | 'money' | 'quantity'

export type TrackerGroup = {
  id: string
  name: string
  kind: TrackerKind
  color: string | null
  position: number
  tracker_count: number
  created_at: string | null
  updated_at: string | null
}

export type Tracker = {
  id: string
  name: string
  kind: TrackerKind
  direction: TrackerDirection
  input_mode: TrackerInputMode
  group_id: string | null
  unit: string | null
  color: string | null
  is_private: boolean
  last_entry_at: string | null
  entry_count_30d: number
  created_at: string | null
  updated_at: string | null
}

export type Entry = {
  id: string
  tracker_id: string
  occurred_at: string | null
  quantity: number | null
  amount: number | null
  list_amount: number | null
  note_md: string | null
  created_at: string | null
  updated_at: string | null
}

export type DashboardResponse = {
  period_start: string
  period_end: string
  current_period_days: number
  prev_period_days: number
  prev_period_truncated: boolean
  corrupted_entry_count: number
  f1_total: number
  f2_current: number
  f2_previous: number
  f3_groups: Array<{ name: string; total: number; trackers: Array<{ tracker_id: string; name: string | null; total: number }> }>
  f4_top: Array<{ entry_id: string; tracker_id: string; tracker_name: string; amount: number }>
  f5_net: number
  a2_gap: Array<{ tracker_id: string; current_days: number | null; avg_days: number | null; enough: boolean }>
  a3_counts: { week: number; month: number; year: number }
  a4_trend: { current_month: number; prev_avg: number; trend: 'up' | 'down' | 'flat' }
}

export const trackerInvalidationKey = ['tracker'] as const

export function trackerQueryKey(kind: 'groups' | 'trackers' | 'entries' | 'dashboard') {
  return ['tracker', kind] as const
}

/** Grid order, frozen per mount (spec §5.2): count desc, then last entry, then name. */
export function sortTrackersForGrid(trackers: Tracker[]): Tracker[] {
  return [...trackers].sort((left, right) => {
    if (left.entry_count_30d !== right.entry_count_30d) {
      return right.entry_count_30d - left.entry_count_30d
    }
    const leftAt = left.last_entry_at ? Date.parse(left.last_entry_at) : 0
    const rightAt = right.last_entry_at ? Date.parse(right.last_entry_at) : 0
    if (leftAt !== rightAt) return rightAt - leftAt
    return left.name.localeCompare(right.name, 'vi')
  })
}

/** Accept digits only; separators are stripped before the server ever sees them. */
export function digitsOnly(value: string): string {
  return value.replace(/\D/g, '')
}

const vndFormatter = new Intl.NumberFormat('vi-VN')

export function formatVnd(amount: number): string {
  return `${vndFormatter.format(amount)} ₫`
}

export function canSubmitAmount(input: string): boolean {
  return input.length > 0
}

export function amountToNumber(input: string): number {
  return Number(digitsOnly(input))
}

/** Last-seen label for A1 on the capture button, computed in Vietnam time. */
export function formatLastSeen(value: string | null, now = new Date()): string {
  if (!value) return 'Chưa ghi'
  const elapsedMs = now.getTime() - Date.parse(value)
  if (elapsedMs < 0) return 'Vừa xong'
  const minutes = Math.floor(elapsedMs / 60_000)
  if (minutes < 1) return 'Vừa xong'
  if (minutes < 60) return `${minutes} phút trước`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} giờ trước`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days} ngày trước`
  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: VIETNAM_TIME_ZONE,
    day: '2-digit',
    month: '2-digit',
  }).format(new Date(value))
}

/** Two quick backdate choices plus a custom picker; all offsets are +07:00. */
export function backdateOptions(now = new Date()): Array<{ label: string; value: string }> {
  const options = [
    { label: 'Hôm qua', value: new Date(now.getTime() - 24 * 3_600_000) },
    { label: '2 giờ trước', value: new Date(now.getTime() - 2 * 3_600_000) },
  ]
  return options.map(({ label, value }) => ({ label, value: toVietnamInput(value) }))
}

function toVietnamInput(value: Date): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: VIETNAM_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  })
    .formatToParts(value)
    .filter(({ type }) => type !== 'literal')
    .reduce<Record<string, string>>((result, part) => {
      result[part.type] = part.value
      return result
    }, {})
  return vietnamInputToIso(`${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`)
}

/** Current month key for the dashboard, always in +07:00 (spec §5.4). */
export function currentVietnamMonth(now = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: VIETNAM_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
  })
    .formatToParts(now)
    .filter(({ type }) => type !== 'literal')
    .reduce<Record<string, string>>((result, part) => {
      result[part.type] = part.value
      return result
    }, {})
  return `${parts.year}-${parts.month}`
}

export type EntryCreatePayload = {
  id: string
  tracker_id: string
  occurred_at?: string
  quantity?: number
  amount?: number
  list_amount?: number
  note_md?: string
}

/** Build the one-tap capture payload for a tracker from the single number input. */
export function capturePayload(
  tracker: Tracker,
  input: string,
  occurredAt?: string,
): EntryCreatePayload {
  const payload: EntryCreatePayload = { id: uuidv7(), tracker_id: tracker.id }
  if (occurredAt) payload.occurred_at = occurredAt
  if (tracker.input_mode === 'money' && input) {
    payload.amount = amountToNumber(input)
  } else if (tracker.input_mode === 'quantity' && input) {
    payload.quantity = amountToNumber(input)
  }
  return payload
}

/** Seam: every tracker write goes through these mutations (017 wraps this one door). */
export function useTrackerWrites(refresh: () => void) {
  const createGroup = useMutation({
    mutationFn: (payload: { id?: string; name: string; kind: TrackerKind }) =>
      apiRequest<TrackerGroup>('/api/tracker/groups', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: refresh,
  })
  const updateGroup = useMutation({
    mutationFn: ({
      groupId,
      payload,
    }: {
      groupId: string
      payload: Partial<Pick<TrackerGroup, 'name' | 'color' | 'position'>>
    }) =>
      apiRequest<TrackerGroup>(`/api/tracker/groups/${groupId}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    onSuccess: refresh,
  })
  const deleteGroup = useMutation({
    mutationFn: (groupId: string) =>
      apiRequest<void>(`/api/tracker/groups/${groupId}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })
  const createTracker = useMutation({
    mutationFn: (payload: {
      id?: string
      name: string
      kind: TrackerKind
      direction?: TrackerDirection
      input_mode?: TrackerInputMode
      group_id?: string | null
      unit?: string | null
      is_private?: boolean
    }) =>
      apiRequest<Tracker>('/api/tracker/trackers', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: refresh,
  })
  const updateTracker = useMutation({
    mutationFn: ({
      trackerId,
      payload,
    }: {
      trackerId: string
      payload: Partial<Pick<Tracker, 'name' | 'kind' | 'direction' | 'input_mode' | 'group_id' | 'unit' | 'is_private'>>
    }) =>
      apiRequest<Tracker>(`/api/tracker/trackers/${trackerId}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    onSuccess: refresh,
  })
  const archiveTracker = useMutation({
    mutationFn: (trackerId: string) =>
      apiRequest<void>(`/api/tracker/trackers/${trackerId}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })
  const restoreTracker = useMutation({
    mutationFn: (trackerId: string) =>
      apiRequest<{ id: string; status: 'restored' }>(
        `/api/tracker/trackers/${trackerId}/restore`,
        { method: 'POST' },
      ),
    onSuccess: refresh,
  })
  const createEntry = useMutation({
    mutationFn: (payload: EntryCreatePayload) =>
      apiRequest<Entry>('/api/tracker/entries', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: refresh,
  })
  const updateEntry = useMutation({
    mutationFn: ({
      entryId,
      payload,
    }: {
      entryId: string
      payload: Partial<Pick<Entry, 'occurred_at' | 'quantity' | 'amount' | 'list_amount' | 'note_md'>>
    }) =>
      apiRequest<Entry>(`/api/tracker/entries/${entryId}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    onSuccess: refresh,
  })
  const deleteEntry = useMutation({
    mutationFn: (entryId: string) =>
      apiRequest<void>(`/api/tracker/entries/${entryId}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })
  const restoreEntry = useMutation({
    mutationFn: (entryId: string) =>
      apiRequest<{ id: string; status: 'restored' }>(
        `/api/tracker/entries/${entryId}/restore`,
        { method: 'POST' },
      ),
    onSuccess: refresh,
  })
  return {
    createGroup,
    updateGroup,
    deleteGroup,
    createTracker,
    updateTracker,
    archiveTracker,
    restoreTracker,
    createEntry,
    updateEntry,
    deleteEntry,
    restoreEntry,
  }
}
