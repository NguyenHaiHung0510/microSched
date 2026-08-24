/** Pure task-form state rules kept testable without a browser runtime. */

import { toVietnamDateTimeInput, vietnamInputToIso } from '@/calendar-ui'

export type TaskStatus = 'open' | 'completed'
export type TaskFilter = TaskStatus | 'all'
export type TaskPriority = 'p1' | 'p2' | 'p3'
export type TaskDuePrecision = 'none' | 'date' | 'datetime'

export type TaskSchedule = {
  due_precision: TaskDuePrecision
  due_on: string | null
  due_at: string | null
}

export type TaskFormState = {
  title: string
  body: string
  priority: TaskPriority | ''
  duePrecision: TaskDuePrecision
  dueOn: string
  dueTime: string
  isPrivate: boolean
}

export type TaskWritePayload = {
  title: string
  body_md: string | null
  priority: TaskPriority | null
  is_private: boolean
} & TaskSchedule

export type TaskPayload = TaskWritePayload & {
  id: string
}

const vietnamDayFormatter = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Ho_Chi_Minh',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

function vietnamDayKey(value: Date): string {
  const values = Object.fromEntries(
    vietnamDayFormatter
      .formatToParts(value)
      .filter(({ type }) => type !== 'literal')
      .map(({ type, value: part }) => [type, part]),
  )
  return `${values.year}-${values.month}-${values.day}`
}

export const taskInvalidationKey = ['tasks'] as const

export function taskQueryKey(filter: TaskFilter) {
  return ['tasks', filter] as const
}

export function taskPayload(state: TaskFormState): TaskWritePayload {
  let schedule: TaskSchedule
  if (state.duePrecision === 'date') {
    schedule = { due_precision: 'date', due_on: state.dueOn, due_at: null }
  } else if (state.duePrecision === 'datetime') {
    schedule = {
      due_precision: 'datetime',
      due_on: null,
      due_at: state.dueOn && state.dueTime
        ? vietnamInputToIso(`${state.dueOn}T${state.dueTime}`)
        : null,
    }
  } else {
    schedule = { due_precision: 'none', due_on: null, due_at: null }
  }
  return {
    title: state.title,
    body_md: state.body || null,
    priority: state.priority || null,
    is_private: state.isPrivate,
    ...schedule,
  }
}

export function canSubmitTask(
  title: string,
  pending: boolean,
  schedule?: Pick<TaskFormState, 'duePrecision' | 'dueOn' | 'dueTime'>,
): boolean {
  if (title.trim().length === 0 || pending) return false
  if (!schedule) return true
  if (schedule.duePrecision === 'date') return schedule.dueOn.length > 0
  if (schedule.duePrecision === 'datetime') {
    return schedule.dueOn.length > 0 && schedule.dueTime.length > 0
  }
  return true
}

export function transitionTaskDuePrecision(
  current: Pick<TaskFormState, 'duePrecision' | 'dueOn' | 'dueTime'>,
  next: TaskDuePrecision,
  today: string,
): Pick<TaskFormState, 'duePrecision' | 'dueOn' | 'dueTime'> {
  if (next === current.duePrecision) return current
  if (next === 'none') return { duePrecision: 'none', dueOn: '', dueTime: '' }
  if (next === 'date') {
    return { duePrecision: 'date', dueOn: current.dueOn || today, dueTime: '' }
  }
  return { duePrecision: 'datetime', dueOn: current.dueOn || today, dueTime: '' }
}

export function scheduleDay(schedule: TaskSchedule): string | null {
  if (schedule.due_precision === 'date') return schedule.due_on
  if (schedule.due_precision === 'datetime' && schedule.due_at) {
    return vietnamDayKey(new Date(schedule.due_at))
  }
  return null
}

export function isTaskScheduleOverdue(
  schedule: TaskSchedule,
  now: Date = new Date(),
): boolean {
  if (schedule.due_precision === 'date') {
    return Boolean(schedule.due_on && schedule.due_on < vietnamDayKey(now))
  }
  return schedule.due_precision === 'datetime'
    && schedule.due_at !== null
    && Date.parse(schedule.due_at) < now.getTime()
}

export function rescheduleTaskSchedule(
  schedule: TaskSchedule,
  targetDay: string,
): TaskSchedule {
  if (schedule.due_precision === 'datetime' && schedule.due_at) {
    const local = toVietnamDateTimeInput(schedule.due_at)
    const time = local.split('T')[1]
    return {
      due_precision: 'datetime',
      due_on: null,
      due_at: vietnamInputToIso(`${targetDay}T${time}`),
    }
  }
  return { due_precision: 'date', due_on: targetDay, due_at: null }
}

export function compareTaskScheduleKey<T extends TaskSchedule & {
  pinned: boolean
  created_at?: string | null
  id: string
}>(
  left: T,
  right: T,
  group: 'dated' | 'overdue' | 'undated' | 'open_picker' = 'open_picker',
): number {
  const leftDay = scheduleDay(left)
  const rightDay = scheduleDay(right)
  const leftGroup = leftDay === null ? 2 : 1
  const rightGroup = rightDay === null ? 2 : 1
  if (leftGroup !== rightGroup) return leftGroup - rightGroup
  if (group !== 'overdue') {
    const groupDayOrder = (leftDay ?? '').localeCompare(rightDay ?? '')
    if (groupDayOrder !== 0) return groupDayOrder
  }
  if (left.pinned !== right.pinned) return left.pinned ? -1 : 1
  const scheduleDayOrder = (leftDay ?? '').localeCompare(rightDay ?? '')
  if (scheduleDayOrder !== 0) return scheduleDayOrder
  const precisionRank = (value: TaskDuePrecision) => value === 'datetime' ? 0 : value === 'date' ? 1 : 2
  const precisionOrder = precisionRank(left.due_precision) - precisionRank(right.due_precision)
  if (precisionOrder !== 0) return precisionOrder
  const dueOrder = (left.due_at ?? '').localeCompare(right.due_at ?? '')
  if (dueOrder !== 0) return dueOrder
  const createdOrder = (right.created_at ?? '').localeCompare(left.created_at ?? '')
  return createdOrder || left.id.localeCompare(right.id)
}

export function toggledStatus(completed: boolean): TaskStatus {
  return completed ? 'completed' : 'open'
}
