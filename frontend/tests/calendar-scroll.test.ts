import assert from 'node:assert/strict'
import { test } from 'vitest'

import type { CalendarEvent } from '../src/calendar-ui'
import {
  annotationDays,
  annotationsByDay,
  dedupeById,
  endOfDayVietnam,
  eventsByDay,
  formatFullVietnameseDate,
  lastDayOfMonth,
  mergeDayChips,
  monthFetchRange,
  monthWeeks,
  sourceTone,
  vnDayKey,
} from '../src/calendar-scroll'

function event(
  id: string,
  starts_at: string,
  ends_at: string,
  extra: Partial<CalendarEvent> = {},
): CalendarEvent {
  return {
    id,
    source_id: 'source-1',
    title: id,
    starts_at,
    ends_at,
    all_day: false,
    location: null,
    description_md: null,
    created_at: null,
    updated_at: null,
    ...extra,
  }
}

function task(id: string, due_at: string | null) {
  return { id, title: id, status: 'open' as const, due_at, created_at: null }
}

function annotation(id: string, starts_on: string, ends_on: string) {
  return {
    id,
    starts_on,
    ends_on,
    label: id,
    note_md: null,
    color: null,
    is_private: false,
    created_at: null,
    updated_at: null,
  }
}

test('ⓐ February 2026 weeks start on Monday with an exact row count', () => {
  const weeks = monthWeeks(2026, 2)
  assert.equal(weeks.length, 5)
  assert.deepEqual(
    weeks.map((week) => week.key),
    ['2026-02-w0', '2026-02-w1', '2026-02-w2', '2026-02-w3', '2026-02-w4'],
  )
  assert.equal(weeks[0].days[0], '2026-01-26')
  assert.equal(weeks[0].days[6], '2026-02-01')
  assert.equal(weeks[4].days[0], '2026-02-23')
  assert.equal(weeks[4].days[6], '2026-03-01')
  // A Sunday-first convention would start the first row on 2026-01-25.
  assert.notEqual(weeks[0].days[0], '2026-01-25')
  assert.ok(weeks.every((week) => week.days.length === 7))
})

test('ⓑ events land on their Vietnam day regardless of the device zone', () => {
  const late = event('late', '2026-08-15T23:30:00+07:00', '2026-08-15T23:45:00+07:00')
  const early = event('early', '2026-08-16T00:30:00+07:00', '2026-08-16T01:00:00+07:00')
  const utcLate = event('utc-late', '2026-08-15T16:30:00Z', '2026-08-15T16:45:00Z')
  const utcEarly = event('utc-early', '2026-08-15T17:30:00Z', '2026-08-15T18:00:00Z')

  const groups = eventsByDay([late, early, utcLate, utcEarly])
  assert.deepEqual([...groups.keys()].sort(), ['2026-08-15', '2026-08-16'])
  assert.deepEqual(
    groups.get('2026-08-15')?.map((entry) => entry.id),
    ['late', 'utc-late'],
  )
  assert.deepEqual(
    groups.get('2026-08-16')?.map((entry) => entry.id),
    ['early', 'utc-early'],
  )
  assert.equal(vnDayKey('2026-08-15T23:30:00+07:00'), '2026-08-15')
  assert.equal(vnDayKey('2026-08-15T17:30:00Z'), '2026-08-16')
})

test('ⓒ an event crossing midnight appears on both calendar days', () => {
  const crossing = event(
    'cross',
    '2026-08-15T23:00:00+07:00',
    '2026-08-16T01:00:00+07:00',
  )
  const groups = eventsByDay([crossing])
  assert.deepEqual(
    groups.get('2026-08-15')?.map((entry) => entry.id),
    ['cross'],
  )
  assert.deepEqual(
    groups.get('2026-08-16')?.map((entry) => entry.id),
    ['cross'],
  )
})

test('ⓓ a 20/08-25/08 annotation covers all six days', () => {
  assert.deepEqual(annotationDays(annotation('a1', '2026-08-20', '2026-08-25')), [
    '2026-08-20',
    '2026-08-21',
    '2026-08-22',
    '2026-08-23',
    '2026-08-24',
    '2026-08-25',
  ])
  const groups = annotationsByDay([annotation('a1', '2026-08-20', '2026-08-25')])
  assert.equal(groups.size, 6)
  assert.deepEqual(
    groups.get('2026-08-24')?.map((entry) => entry.id),
    ['a1'],
  )
})

test('ⓔ month fetch ranges are half-open with no gap or overlap', () => {
  assert.deepEqual(monthFetchRange(2026, 8), {
    from: '2026-08-01T00:00:00+07:00',
    to: '2026-09-01T00:00:00+07:00',
  })
  assert.deepEqual(monthFetchRange(2026, 12), {
    from: '2026-12-01T00:00:00+07:00',
    to: '2027-01-01T00:00:00+07:00',
  })
  const august = monthFetchRange(2026, 8)
  const september = monthFetchRange(2026, 9)
  assert.equal(august.to, september.from)
})

test('ⓕ an event returned by two adjacent month queries counts once', () => {
  const crossing = event(
    'cross',
    '2026-08-31T23:00:00+07:00',
    '2026-09-01T01:00:00+07:00',
  )
  const other = event('other', '2026-08-15T07:00:00+07:00', '2026-08-15T08:00:00+07:00')
  const august = eventsByDay([crossing, other])
  const september = eventsByDay([crossing])
  const merged = eventsByDay([...august.values(), ...september.values()].flat())
  const ids = new Set([...merged.values()].flat().map((entry) => entry.id))
  assert.deepEqual([...ids].sort(), ['cross', 'other'])
  assert.deepEqual(
    dedupeById([{ id: 'cross' }, { id: 'other' }, { id: 'cross' }]).map((entry) => entry.id),
    ['cross', 'other'],
  )
})

test('ⓖ chips merge events before tasks and collapse into one +N', () => {
  const e1 = event('e1', '2026-08-15T07:00:00+07:00', '2026-08-15T08:00:00+07:00')
  const e2 = event('e2', '2026-08-15T08:00:00+07:00', '2026-08-15T09:00:00+07:00')
  const e3 = event('e3', '2026-08-15T09:00:00+07:00', '2026-08-15T10:00:00+07:00')
  const t1 = task('t1', '2026-08-15T23:59:00+07:00')
  const t2 = task('t2', '2026-08-15T23:59:00+07:00')

  const mobile = mergeDayChips([e1, e2, e3], [t1, t2], 2)
  assert.deepEqual(mobile.chips.map((chip) => chip.kind), ['event', 'event'])
  assert.deepEqual(
    mobile.chips.map((chip) => (chip.kind === 'event' ? chip.event.id : chip.task.id)),
    ['e1', 'e2'],
  )
  assert.equal(mobile.overflow, 3)

  const desktop = mergeDayChips([e1, e2, e3], [t1, t2], 3)
  assert.deepEqual(
    desktop.chips.map((chip) => (chip.kind === 'event' ? chip.event.id : chip.task.id)),
    ['e1', 'e2', 'e3'],
  )
  assert.equal(desktop.overflow, 2)
})

test('ⓗ a day with one task renders one task chip and no +N line', () => {
  const result = mergeDayChips([], [task('t1', '2026-08-15T23:59:00+07:00')], 2)
  assert.equal(result.chips.length, 1)
  assert.equal(result.chips[0].kind, 'task')
  assert.equal(result.overflow, 0)
})

test('endOfDayVietnam pins the deadline to 23:59+07:00', () => {
  assert.equal(endOfDayVietnam('2026-08-15'), '2026-08-15T23:59:00+07:00')
})

test('the full Vietnamese date for 15/08/2026 is Thứ Bảy (spec §5.5 example)', () => {
  assert.equal(formatFullVietnameseDate('2026-08-15'), 'Thứ Bảy, 15/08/2026')
})

test('lastDayOfMonth handles leap and short months', () => {
  assert.equal(lastDayOfMonth(2026, 2), '2026-02-28')
  assert.equal(lastDayOfMonth(2028, 2), '2028-02-29')
  assert.equal(lastDayOfMonth(2026, 12), '2026-12-31')
})

test('sourceTone maps every SOURCE_COLORS key to existing tokens', () => {
  assert.deepEqual(sourceTone('rose'), {
    background: 'var(--rose-100)',
    color: 'var(--rose-700)',
  })
  assert.deepEqual(sourceTone(null), {
    background: 'var(--n-100)',
    color: 'var(--n-700)',
  })
  for (const key of ['rose', 'amber', 'emerald', 'sky', 'violet', 'slate']) {
    assert.match(sourceTone(key).background, /^var\(--/)
    assert.match(sourceTone(key).color, /^var\(--/)
  }
})
