import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'vitest'

import {
  canSubmitTask,
  compareTaskScheduleKey,
  isTaskScheduleOverdue,
  rescheduleTaskSchedule,
  taskInvalidationKey,
  taskPayload,
  taskQueryKey,
  toggledStatus,
  transitionTaskDuePrecision,
  type TaskSchedule,
} from '../src/task-ui.ts'

type SortBucket = 'dated' | 'overdue' | 'undated' | 'open_picker'
type SortFixture = {
  rows: Array<TaskSchedule & {
    id: string
    title: string
    pinned: boolean
    created_at: string
  }>
  buckets: Record<SortBucket, string[]>
}

const sortFixture = JSON.parse(
  readFileSync(
    new URL('../../tests/fixtures/task_schedule_order.json', import.meta.url),
    'utf8',
  ),
) as SortFixture

test('task form normalizes optional values at the API boundary', () => {
  assert.deepEqual(
    taskPayload({
      title: 'Chuẩn bị họp',
      body: '',
      priority: '',
      duePrecision: 'none',
      dueOn: '',
      dueTime: '',
      isPrivate: true,
    }),
    {
      title: 'Chuẩn bị họp',
      body_md: null,
      priority: null,
      due_precision: 'none',
      due_on: null,
      due_at: null,
      is_private: true,
    },
  )
})

test('date-only and datetime payloads preserve their honest precision', () => {
  assert.deepEqual(
    taskPayload({
      title: 'Ngày thôi', body: '', priority: '', isPrivate: false,
      duePrecision: 'date', dueOn: '2026-08-24', dueTime: '',
    }),
    {
      title: 'Ngày thôi', body_md: null, priority: null, is_private: false,
      due_precision: 'date', due_on: '2026-08-24', due_at: null,
    },
  )
  assert.deepEqual(
    taskPayload({
      title: 'Có giờ', body: '', priority: '', isPrivate: false,
      duePrecision: 'datetime', dueOn: '2026-08-24', dueTime: '09:30',
    }),
    {
      title: 'Có giờ', body_md: null, priority: null, is_private: false,
      due_precision: 'datetime', due_on: null, due_at: '2026-08-24T09:30:00+07:00',
    },
  )
})

test('precision transitions never invent a clock time', () => {
  assert.deepEqual(
    transitionTaskDuePrecision(
      { duePrecision: 'none', dueOn: '', dueTime: '' },
      'datetime',
      '2026-08-24',
    ),
    { duePrecision: 'datetime', dueOn: '2026-08-24', dueTime: '' },
  )
  assert.deepEqual(
    transitionTaskDuePrecision(
      { duePrecision: 'datetime', dueOn: '2026-08-25', dueTime: '14:20' },
      'date',
      '2026-08-24',
    ),
    { duePrecision: 'date', dueOn: '2026-08-25', dueTime: '' },
  )
  assert.deepEqual(
    transitionTaskDuePrecision(
      { duePrecision: 'datetime', dueOn: '2026-08-25', dueTime: '14:20' },
      'datetime',
      '2026-08-24',
    ),
    { duePrecision: 'datetime', dueOn: '2026-08-25', dueTime: '14:20' },
  )
})

test('date-only is overdue only after its Vietnam civil day ends', () => {
  const schedule = { due_precision: 'date' as const, due_on: '2026-08-24', due_at: null }
  assert.equal(isTaskScheduleOverdue(schedule, new Date('2026-08-24T16:59:59Z')), false)
  assert.equal(isTaskScheduleOverdue(schedule, new Date('2026-08-24T17:00:00Z')), true)
})

test('reschedule preserves datetime clock, date precision, and promotes none to date', () => {
  assert.deepEqual(
    rescheduleTaskSchedule(
      { due_precision: 'datetime', due_on: null, due_at: '2026-08-24T09:30:00+07:00' },
      '2026-08-27',
    ),
    { due_precision: 'datetime', due_on: null, due_at: '2026-08-27T09:30:00+07:00' },
  )
  assert.deepEqual(
    rescheduleTaskSchedule(
      { due_precision: 'date', due_on: '2026-08-24', due_at: null },
      '2026-08-27',
    ),
    { due_precision: 'date', due_on: '2026-08-27', due_at: null },
  )
  assert.deepEqual(
    rescheduleTaskSchedule(
      { due_precision: 'none', due_on: null, due_at: null },
      '2026-08-27',
    ),
    { due_precision: 'date', due_on: '2026-08-27', due_at: null },
  )
})

test('the shared contract fixture keeps group day before pin except in overdue', () => {
  for (const [bucket, expected] of Object.entries(sortFixture.buckets) as Array<[
    SortBucket,
    string[],
  ]>) {
    const included = new Set(expected)
    const actual = sortFixture.rows
      .filter(({ title }) => included.has(title))
      .sort((left, right) => compareTaskScheduleKey(left, right, bucket))
      .map(({ title }) => title)
    assert.deepEqual(actual, expected, bucket)
  }
})

test('task query keys separate filters while mutations invalidate the family', () => {
  assert.deepEqual(taskQueryKey('open'), ['tasks', 'open'])
  assert.deepEqual(taskQueryKey('completed'), ['tasks', 'completed'])
  assert.deepEqual(taskInvalidationKey, ['tasks'])
})

test('pending submit is disabled so a fast second click cannot duplicate a task', () => {
  assert.equal(canSubmitTask('Việc mới', false), true)
  assert.equal(canSubmitTask('Việc mới', true), false)
  assert.equal(canSubmitTask('', false), false)
  assert.equal(canSubmitTask('   ', false), false)
  assert.equal(canSubmitTask('Có giờ', false, {
    duePrecision: 'datetime', dueOn: '2026-08-24', dueTime: '',
  }), false)
})

test('completion checkbox maps to the two API status values', () => {
  assert.equal(toggledStatus(true), 'completed')
  assert.equal(toggledStatus(false), 'open')
})
