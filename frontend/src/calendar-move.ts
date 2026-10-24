import { apiRequest } from '@/api'
import { addVietnamDays } from '@/calendar-ui'
import { vnDayKey, type CalendarTask, type DayAnnotation } from '@/calendar-scroll'
import { barrier, getSnapshot, subscribe, unlocked } from '@/outbox/core'
import { taskRequest } from '@/outbox/adapters'
import type { TaskSchedule } from '@/task-ui'

export type CalendarMoveTarget =
  | { kind: 'task'; item: CalendarTask; grabbedDay: string }
  | { kind: 'annotation'; item: DayAnnotation; grabbedDay: string }

export function validMoveDay(day: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(day) && day.slice(0, 4) !== '0000' &&
    Number.isFinite(Date.parse(day + 'T00:00:00Z')) && new Date(day + 'T00:00:00Z').toISOString().slice(0, 10) === day
}

export function taskSchedule(task: TaskSchedule): TaskSchedule {
  return { due_precision: task.due_precision, due_on: task.due_on, due_at: task.due_at }
}

export function shiftedTaskSchedule(task: TaskSchedule, day: string): TaskSchedule {
  if (!validMoveDay(day)) throw Error('Chọn ngày hợp lệ.')
  if (task.due_precision === 'datetime' && task.due_at) {
    const delta = Date.parse(day + 'T00:00:00Z') - Date.parse(vnDayKey(task.due_at) + 'T00:00:00Z')
    return { due_precision: 'datetime', due_on: null, due_at: new Date(Date.parse(task.due_at) + delta).toISOString() }
  }
  return { due_precision: 'date', due_on: day, due_at: null }
}

export function shiftedAnnotation(annotation: Pick<DayAnnotation, 'starts_on' | 'ends_on'>, grabbedDay: string, day: string) {
  if (![grabbedDay, day].every(validMoveDay) || grabbedDay < annotation.starts_on || grabbedDay > annotation.ends_on) throw Error('Chọn ngày hợp lệ trong dấu ngày.')
  const delta = (Date.parse(day + 'T00:00:00Z') - Date.parse(grabbedDay + 'T00:00:00Z')) / 86400000
  return { starts_on: addVietnamDays(annotation.starts_on, delta), ends_on: addVietnamDays(annotation.ends_on, delta) }
}

export function assertCalendarMoveOnline(isPrivate: boolean) {
  const { context, authRequired } = getSnapshot()
  if (navigator.onLine === false) throw Error('Kết nối mạng để chuyển ngày. Nội dung chưa đổi.')
  if (authRequired || !context.verified || context.expires <= Date.now()) throw Error('Đăng nhập lại để chuyển ngày.')
  if (isPrivate && !unlocked()) throw Error('Mở khoá riêng tư trước khi chuyển ngày.')
}

/** Observe the existing core; never drain, retry, remove or reorder its commands here. */
export function waitForCalendarTaskAck(id: string, isPrivate: boolean): Promise<void> {
  return new Promise((resolve, reject) => {
    let dispose = () => {}
    const finish = (error?: Error) => {
      clearTimeout(timer); dispose(); window.removeEventListener('offline', offline)
      window.removeEventListener('microsched:visibility', check)
      if (error) reject(error); else resolve()
    }
    const check = () => {
      try {
        assertCalendarMoveOnline(isPrivate)
        const snapshot = getSnapshot(), aggregate = 'task:' + id
        const rows = snapshot.rows.filter(r => r.aggregate === aggregate && r.principal === snapshot.context.principal)
        if (rows.some(r => ['held', 'rejected', 'unknown'].includes(r.state))) {
          finish(Error('Chuyển ngày chưa được xác minh. Kiểm tra thay đổi đang chờ trước khi thử lại.'))
        } else if (!rows.length && !snapshot.reconciling.includes(aggregate)) finish()
      } catch (error) { finish(error as Error) }
    }
    const offline = () => finish(Error('Mất kết nối. Thay đổi đang chờ xác minh; chưa báo đã lưu.'))
    const timer = setTimeout(() => finish(Error('Chưa xác minh được lưu. Giữ thay đổi đang chờ và kiểm tra kết nối.')), 30000)
    dispose = subscribe(check)
    window.addEventListener('offline', offline)
    window.addEventListener('microsched:visibility', check)
    check()
  })
}

export async function moveCalendarTask(task: CalendarTask, schedule: TaskSchedule): Promise<CalendarTask> {
  assertCalendarMoveOnline(task.is_private)
  await barrier('task:' + task.id)
  assertCalendarMoveOnline(task.is_private)
  await taskRequest(`/api/tasks/${task.id}`, { method: 'PATCH', body: JSON.stringify(schedule) })
  await waitForCalendarTaskAck(task.id, task.is_private)
  const canonical = await apiRequest<CalendarTask>(`/api/tasks/${task.id}`)
  assertCalendarMoveOnline(task.is_private)
  if (canonical.due_precision !== schedule.due_precision || canonical.due_on !== schedule.due_on ||
      (schedule.due_at ? Date.parse(canonical.due_at ?? '') !== Date.parse(schedule.due_at) : canonical.due_at !== null))
    throw Error('Lịch đã thay đổi. Tải lại trước khi chuyển tiếp.')
  return canonical
}
