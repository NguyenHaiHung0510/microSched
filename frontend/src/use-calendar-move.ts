import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'
import { toast } from 'sonner'
import { apiRequest } from '@/api'
import { importErrorMessage } from '@/calendar-ui'
import type { CalendarTask, DayAnnotation } from '@/calendar-scroll'
import { assertCalendarMoveOnline, moveCalendarTask, shiftedAnnotation, shiftedTaskSchedule, taskSchedule, type CalendarMoveTarget } from '@/calendar-move'
import { unlocked } from '@/outbox/core'
import { reminderKey } from '@/reminder-ui'
import type { TaskSchedule } from '@/task-ui'

type Dates = Pick<DayAnnotation, 'starts_on' | 'ends_on'>
type Operation =
  | { kind: 'task'; item: CalendarTask; before: TaskSchedule; after: TaskSchedule; undo?: boolean }
  | { kind: 'annotation'; item: DayAnnotation; before: Dates; after: Dates; undo?: boolean }

export function useCalendarMove() {
  const client = useQueryClient()
  const inFlight = useRef(false)
  function updateAnnotation(id: string, dates: Dates) {
    client.setQueriesData<{ items: DayAnnotation[] }>({ queryKey: ['calendar', 'annotations'] }, old => old
      ? { ...old, items: old.items.map(item => item.id === id ? { ...item, ...dates } : item) } : old)
  }
  const mutation = useMutation({
    networkMode: 'always',
    mutationFn: async (operation: Operation) => {
      assertCalendarMoveOnline(operation.item.is_private)
      if (operation.kind === 'task') return moveCalendarTask(operation.item, operation.after)
      const row = await apiRequest<DayAnnotation>(`/api/calendar/annotations/${operation.item.id}`, {
        method: 'PATCH', body: JSON.stringify(operation.after),
      })
      if (row.starts_on !== operation.after.starts_on || row.ends_on !== operation.after.ends_on)
        throw Error('Ngày lưu chưa khớp. Tải lại trước khi chuyển tiếp.')
      return row
    },
    onMutate: async operation => {
      assertCalendarMoveOnline(operation.item.is_private)
      if (operation.kind === 'annotation') {
        await client.cancelQueries({ queryKey: ['calendar', 'annotations'] })
        assertCalendarMoveOnline(operation.item.is_private)
        updateAnnotation(operation.item.id, operation.after)
        return { optimistic: true }
      }
      return { optimistic: false }
    },
    onSuccess: (_data, operation) => {
      if (operation.item.is_private && !unlocked()) return
      toast('Đã chuyển ngày', operation.undo ? undefined : {
        duration: 8000,
        action: { label: 'Hoàn tác', onClick: () => submitOperation({ ...operation,
          before: operation.after, after: operation.before, undo: true } as Operation) },
      })
    },
    onError: (error, operation, context) => {
      if (context?.optimistic && operation.kind === 'annotation' && (!operation.item.is_private || unlocked()))
        updateAnnotation(operation.item.id, operation.before)
      toast.error(importErrorMessage(error))
    },
    onSettled: () => {
      inFlight.current = false
      for (const queryKey of [['calendar'], ['tasks'], reminderKey]) void client.invalidateQueries({ queryKey })
    },
  })
  function submitOperation(operation: Operation, onSuccess?: () => void) {
    if (inFlight.current) { toast.error('Đang chuyển ngày. Đợi xác minh lần chuyển trước.'); return }
    inFlight.current = true
    mutation.mutate(operation, { onSuccess })
  }
  function move(target: CalendarMoveTarget, day: string, onSuccess?: () => void) {
    try {
      const operation: Operation = target.kind === 'task'
        ? { kind: 'task', item: target.item, before: taskSchedule(target.item), after: shiftedTaskSchedule(target.item, day) }
        : { kind: 'annotation', item: target.item,
          before: { starts_on: target.item.starts_on, ends_on: target.item.ends_on },
          after: shiftedAnnotation(target.item, target.grabbedDay, day) }
      submitOperation(operation, onSuccess)
    } catch (error) { toast.error(importErrorMessage(error)) }
  }
  return { ...mutation, move }
}
