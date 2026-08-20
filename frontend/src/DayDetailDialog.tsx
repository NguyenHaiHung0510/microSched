import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Edit3, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { apiRequest } from '@/api'
import {
  formatVietnamTime,
  importErrorMessage,
  sourceColorToken,
  type CalendarEvent,
  type CalendarSource,
} from '@/calendar-ui'
import {
  endOfDayVietnam,
  formatFullVietnameseDate,
  formatShortVietnamDate,
  isTaskOverdue,
  sortOpenTasksForMove,
  type CalendarTask,
  type DayAnnotation,
} from '@/calendar-scroll'
import { AnnotationForm, type AnnotationFormValue } from '@/AnnotationForm'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { EventForm } from '@/EventForm'
import { TaskForm } from '@/TaskForm'
import { cn } from '@/lib/utils'
import type { TaskWritePayload } from '@/task-ui'
import { CALENDAR_FAMILY_KEY } from '@/calendar-queries'

type OpenTaskPage = { items: CalendarTask[]; next_cursor?: string | null }

type EventFormValue = {
  source_id?: string
  title: string
  starts_at: string
  ends_at: string
  all_day: boolean
  location: string | null
  description_md: string | null
}

type EventFormState =
  | { mode: 'create' }
  | { mode: 'edit'; event: CalendarEvent }
  | null

type AnnotationFormState =
  | { mode: 'create' }
  | { mode: 'edit'; annotation: DayAnnotation }
  | null

export function DayDetailDialog({
  open,
  onOpenChange,
  day,
  events,
  tasks,
  loadOpenTasks,
  annotations,
  sourceById,
  privateLocked,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  day: string
  events: CalendarEvent[]
  tasks: CalendarTask[]
  loadOpenTasks: (cursor: string | null) => Promise<OpenTaskPage>
  annotations: DayAnnotation[]
  sourceById: Map<string, CalendarSource>
  privateLocked: boolean
}) {
  const queryClient = useQueryClient()
  const [annotationForm, setAnnotationForm] = useState<AnnotationFormState>(null)
  const [eventForm, setEventForm] = useState<EventFormState>(null)
  const [taskEdit, setTaskEdit] = useState<CalendarTask | null>(null)
  const [moveOpen, setMoveOpen] = useState(false)
  const [moveNow, setMoveNow] = useState(0)
  const [moveTasks, setMoveTasks] = useState<CalendarTask[]>([])
  const [moveCursor, setMoveCursor] = useState<string | null>(null)
  const [moveLoading, setMoveLoading] = useState(false)
  const [moveError, setMoveError] = useState<string | null>(null)
  const [annotationError, setAnnotationError] = useState<string | null>(null)
  const [eventError, setEventError] = useState<string | null>(null)

  const refreshCalendar = () =>
    void queryClient.invalidateQueries({ queryKey: CALENDAR_FAMILY_KEY })
  const refreshAll = () => {
    void queryClient.invalidateQueries({ queryKey: ['tasks'] })
    refreshCalendar()
  }

  const manualSources = useMemo(
    () =>
      [...sourceById.values()].filter(
        (source) => source.kind === 'manual' && source.is_visible,
      ),
    [sourceById],
  )

  const createAnnotation = useMutation({
    mutationFn: (value: AnnotationFormValue) =>
      apiRequest<DayAnnotation>('/api/calendar/annotations', {
        method: 'POST',
        body: JSON.stringify(value),
      }),
    onSuccess: () => {
      setAnnotationForm(null)
      setAnnotationError(null)
      refreshCalendar()
    },
    onError: (error) => setAnnotationError(importErrorMessage(error)),
  })

  const updateAnnotation = useMutation({
    mutationFn: ({ id, value }: { id: string; value: AnnotationFormValue }) =>
      apiRequest<DayAnnotation>(`/api/calendar/annotations/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(value),
      }),
    onSuccess: () => {
      setAnnotationForm(null)
      setAnnotationError(null)
      refreshCalendar()
    },
    onError: (error) => setAnnotationError(importErrorMessage(error)),
  })

  const deleteAnnotation = useMutation({
    mutationFn: (id: string) =>
      apiRequest<void>(`/api/calendar/annotations/${id}`, { method: 'DELETE' }),
    onSuccess: refreshCalendar,
    onError: (error) => setAnnotationError(importErrorMessage(error)),
  })

  const createEvent = useMutation({
    mutationFn: (value: EventFormValue) =>
      apiRequest<CalendarEvent>('/api/calendar/events', {
        method: 'POST',
        body: JSON.stringify(value),
      }),
    onSuccess: () => {
      setEventForm(null)
      setEventError(null)
      refreshCalendar()
    },
    onError: (error) => setEventError(importErrorMessage(error)),
  })

  const updateEvent = useMutation({
    mutationFn: ({ eventId, value }: { eventId: string; value: EventFormValue }) =>
      apiRequest<CalendarEvent>(`/api/calendar/events/${eventId}`, {
        method: 'PATCH',
        body: JSON.stringify(value),
      }),
    onSuccess: () => {
      setEventForm(null)
      setEventError(null)
      refreshCalendar()
    },
    onError: (error) => setEventError(importErrorMessage(error)),
  })

  const editTask = useMutation({
    mutationFn: ({ taskId, payload }: { taskId: string; payload: TaskWritePayload }) =>
      apiRequest<CalendarTask>(`/api/tasks/${taskId}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      setTaskEdit(null)
      refreshAll()
    },
  })

  const rescheduleTask = useMutation({
    mutationFn: (variables: {
      taskId: string
      dueAt: string | null
      previousDue: string | null
      showToast: boolean
    }) =>
      apiRequest<CalendarTask>(`/api/tasks/${variables.taskId}`, {
        method: 'PATCH',
        body: JSON.stringify({ due_at: variables.dueAt }),
      }),
    onSuccess: (_data, variables) => {
      refreshAll()
      if (!variables.showToast) return
      toast(
        <span className="block min-w-0 max-w-full break-words">
          Đã dời việc sang {formatShortVietnamDate(day)}
        </span>,
        {
          duration: 8000,
          action: {
            label: 'Hoàn tác',
            onClick: () =>
              rescheduleTask.mutate({
                taskId: variables.taskId,
                dueAt: variables.previousDue,
                previousDue: null,
                showToast: false,
              }),
          },
        },
      )
    },
  })

  function moveTask(task: CalendarTask) {
    setMoveOpen(false)
    rescheduleTask.mutate({
      taskId: task.id,
      dueAt: endOfDayVietnam(day),
      previousDue: task.due_at,
      showToast: true,
    })
  }

  async function openMoveDialog() {
    const now = Date.now()
    setMoveNow(now)
    setMoveTasks([])
    setMoveCursor(null)
    setMoveError(null)
    setMoveOpen(true)
    setMoveLoading(true)
    try {
      const page = await loadOpenTasks(null)
      setMoveTasks(sortOpenTasksForMove(page.items, now))
      setMoveCursor(page.next_cursor ?? null)
    } catch (error) {
      setMoveError(importErrorMessage(error))
    } finally {
      setMoveLoading(false)
    }
  }

  async function loadMoreMoveTasks() {
    if (!moveCursor || moveLoading) return
    setMoveLoading(true)
    setMoveError(null)
    try {
      const page = await loadOpenTasks(moveCursor)
      setMoveTasks((current) => [
        ...current,
        ...sortOpenTasksForMove(page.items, moveNow),
      ])
      setMoveCursor(page.next_cursor ?? null)
    } catch (error) {
      setMoveError(importErrorMessage(error))
    } finally {
      setMoveLoading(false)
    }
  }

  function closeDialog() {
    onOpenChange(false)
    setAnnotationForm(null)
    setEventForm(null)
    setMoveOpen(false)
    setMoveTasks([])
    setMoveCursor(null)
    setMoveError(null)
    setTaskEdit(null)
  }

  const editingIcsEvent =
    eventForm?.mode === 'edit' &&
    sourceById.get(eventForm.event.source_id)?.kind === 'ics'

  return (
    <>
      <Dialog open={open} onOpenChange={(next) => (next ? undefined : closeDialog())}>
        <DialogContent
          data-testid="calendar-day-dialog"
          className="max-h-[85vh] overflow-y-auto sm:max-w-lg"
        >
          <DialogHeader>
            <DialogTitle>{formatFullVietnameseDate(day)}</DialogTitle>
            <DialogDescription>Chi tiết buổi, việc và dấu ngày.</DialogDescription>
          </DialogHeader>

          {annotationForm ? (
            <div className="space-y-3">
              <AnnotationForm
                initial={
                  annotationForm.mode === 'edit' ? annotationForm.annotation : undefined
                }
                defaultStartsOn={annotationForm.mode === 'create' ? day : undefined}
                privateLocked={privateLocked}
                pending={createAnnotation.isPending || updateAnnotation.isPending}
                onSubmit={(value) => {
                  if (annotationForm.mode === 'edit') {
                    updateAnnotation.mutate({
                      id: annotationForm.annotation.id,
                      value,
                    })
                  } else {
                    createAnnotation.mutate(value)
                  }
                }}
                onCancel={() => setAnnotationForm(null)}
              />
              {annotationError ? (
                <p className="text-sm text-bad" role="alert">
                  {annotationError}
                </p>
              ) : null}
            </div>
          ) : (
            <div className="space-y-5">
              <section aria-labelledby="day-annotations-heading" className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h4
                    id="day-annotations-heading"
                    className="text-sm font-bold uppercase tracking-wider text-muted-foreground"
                  >
                    Dấu ngày
                  </h4>
                  <Button
                    data-testid="calendar-day-add-annotation"
                    size="sm"
                    variant="outline"
                    onClick={() => setAnnotationForm({ mode: 'create' })}
                  >
                    <Plus data-icon="inline-start" />
                    Đánh dấu ngày này
                  </Button>
                </div>
                {annotations.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Chưa có dấu ngày nào.</p>
                ) : (
                  annotations.map((annotation) => (
                    <div
                      key={annotation.id}
                      className="flex items-start gap-3 rounded-lg border p-3"
                    >
                      <span
                        aria-hidden="true"
                        className="mt-1 size-3 shrink-0 rounded-full"
                        style={{ backgroundColor: sourceColorToken(annotation.color) }}
                      />
                      <div className="min-w-0 flex-1">
                        <p className="break-words text-sm font-bold">{annotation.label}</p>
                        <p className="text-xs text-muted-foreground">
                          {annotation.starts_on === annotation.ends_on
                            ? formatShortVietnamDate(annotation.starts_on)
                            : `${formatShortVietnamDate(annotation.starts_on)} – ${formatShortVietnamDate(annotation.ends_on)}`}
                        </p>
                        {annotation.note_md ? (
                          <p className="mt-1 break-words whitespace-pre-wrap text-sm text-muted-foreground">
                            {annotation.note_md}
                          </p>
                        ) : null}
                      </div>
                      <div className="flex shrink-0 gap-1">
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          aria-label={`Sửa dấu ${annotation.label}`}
                          onClick={() => setAnnotationForm({ mode: 'edit', annotation })}
                        >
                          <Edit3 />
                        </Button>
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          className="text-bad hover:text-bad"
                          aria-label={`Xoá dấu ${annotation.label}`}
                          disabled={deleteAnnotation.isPending}
                          onClick={() => deleteAnnotation.mutate(annotation.id)}
                        >
                          <Trash2 />
                        </Button>
                      </div>
                    </div>
                  ))
                )}
                {deleteAnnotation.isError ? (
                  <p className="text-sm text-bad" role="alert">
                    {importErrorMessage(deleteAnnotation.error)}
                  </p>
                ) : null}
              </section>

              <section aria-labelledby="day-events-heading" className="space-y-2">
                <h4
                  id="day-events-heading"
                  className="text-sm font-bold uppercase tracking-wider text-muted-foreground"
                >
                  Buổi
                </h4>
                {events.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Không có buổi nào.</p>
                ) : (
                  events.map((event) => {
                    const source = sourceById.get(event.source_id)
                    return (
                      <Button
                        data-testid="calendar-day-event"
                        data-event-id={event.id}
                        key={event.id}
                        variant="ghost"
                        className="h-auto w-full justify-start gap-3 rounded-lg border p-3 text-left"
                        onClick={() => setEventForm({ mode: 'edit', event })}
                      >
                        <span
                          aria-hidden="true"
                          className="size-3 shrink-0 rounded-full"
                          style={{
                            backgroundColor: sourceColorToken(source?.color ?? null),
                          }}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-bold">
                            {event.title}
                          </span>
                          <span className="block truncate text-xs text-muted-foreground">
                            {formatVietnamTime(event)}
                            {event.location ? ` · ${event.location}` : ''}
                          </span>
                        </span>
                      </Button>
                    )
                  })
                )}
              </section>

              <section aria-labelledby="day-tasks-heading" className="space-y-2">
                <h4
                  id="day-tasks-heading"
                  className="text-sm font-bold uppercase tracking-wider text-muted-foreground"
                >
                  Task đến hạn
                </h4>
                {tasks.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Không có task đến hạn hôm nay.</p>
                ) : (
                  tasks.map((task) => (
                    <Button
                      data-testid="calendar-day-task"
                      data-task-id={task.id}
                      key={task.id}
                      variant="ghost"
                      className={cn(
                        'h-auto w-full justify-start gap-3 rounded-lg border p-3 text-left',
                        task.status === 'completed' && 'opacity-70',
                      )}
                      onClick={() => setTaskEdit(task)}
                    >
                      <span
                        className={cn(
                          'min-w-0 flex-1 truncate text-sm font-semibold',
                          task.status === 'completed' && 'line-through',
                        )}
                      >
                        {task.title}
                      </span>
                    </Button>
                  ))
                )}
              </section>

              <div className="flex flex-wrap gap-2 border-t pt-4">
                <Button
                  data-testid="calendar-day-add-event"
                  size="lg"
                  onClick={() => setEventForm({ mode: 'create' })}
                >
                  <Plus data-icon="inline-start" />
                  Thêm buổi vào ngày này
                </Button>
                <Button
                  data-testid="calendar-day-move-task"
                  size="lg"
                  variant="outline"
                  onClick={openMoveDialog}
                >
                  Dời một việc sang ngày này
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={moveOpen} onOpenChange={setMoveOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Dời việc sang ngày này</DialogTitle>
            <DialogDescription>
              Hạn sẽ đặt cuối ngày {formatShortVietnamDate(day)} theo giờ Việt Nam.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            {moveLoading && moveTasks.length === 0 ? (
              <p className="text-sm text-muted-foreground">Đang tải việc…</p>
            ) : moveTasks.length === 0 ? (
              <p className="text-sm text-muted-foreground">Không có việc đang mở.</p>
            ) : (
              moveTasks.map((task) => (
                <Button
                  key={task.id}
                  data-testid="calendar-move-task"
                  data-task-id={task.id}
                  variant="outline"
                  className="h-auto w-full justify-start gap-3 p-3 text-left"
                  disabled={rescheduleTask.isPending}
                  onClick={() => moveTask(task)}
                >
                  <span className="min-w-0 flex-1 truncate text-sm font-semibold">
                    {task.title}
                  </span>
                  {task.due_at ? (
                    <span
                      className={cn(
                        'shrink-0 text-xs',
                        isTaskOverdue(task.due_at, moveNow)
                          ? 'font-bold text-bad'
                          : 'text-muted-foreground',
                      )}
                    >
                      {formatShortVietnamDate(task.due_at.slice(0, 10))}
                    </span>
                  ) : null}
                </Button>
              ))
            )}
            {moveCursor ? (
              <Button
                data-testid="calendar-move-load-more"
                size="lg"
                variant="outline"
                disabled={moveLoading}
                onClick={() => void loadMoreMoveTasks()}
              >
                {moveLoading ? 'Đang tải…' : 'Xem thêm việc'}
              </Button>
            ) : null}
            {moveError ? (
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm text-bad" role="alert">{moveError}</p>
                <Button size="lg" variant="outline" disabled={moveLoading} onClick={() => void (moveCursor ? loadMoreMoveTasks() : openMoveDialog())}>Thử lại</Button>
              </div>
            ) : null}
            {rescheduleTask.isError ? (
              <p className="text-sm text-bad" role="alert">
                {importErrorMessage(rescheduleTask.error)}
              </p>
            ) : null}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={taskEdit !== null} onOpenChange={(next) => !next && setTaskEdit(null)}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Sửa · {taskEdit?.title}</DialogTitle>
            <DialogDescription>Cập nhật nội dung, ưu tiên, hạn hoặc chế độ riêng tư.</DialogDescription>
          </DialogHeader>
          {taskEdit ? (
            <TaskForm
              initial={taskEdit}
              submitLabel="Lưu thay đổi"
              pending={editTask.isPending}
              onSubmit={(payload) =>
                editTask.mutate({ taskId: taskEdit.id, payload })
              }
              onCancel={() => setTaskEdit(null)}
            />
          ) : null}
          {editTask.isError ? (
            <p className="text-sm text-bad" role="alert">
              {importErrorMessage(editTask.error)}
            </p>
          ) : null}
        </DialogContent>
      </Dialog>

      {eventForm ? (
        <EventForm
          open
          onOpenChange={(next) => !next && setEventForm(null)}
          initialEvent={eventForm.mode === 'edit' ? eventForm.event : undefined}
          defaultDate={eventForm.mode === 'create' ? day : undefined}
          allowedSourceIds={manualSources.map((source) => source.id)}
          manualSources={manualSources}
          pending={createEvent.isPending || updateEvent.isPending}
          icsWarning={Boolean(editingIcsEvent)}
          error={eventError}
          onSubmit={(value) => {
            if (eventForm.mode === 'edit') {
              updateEvent.mutate({ eventId: eventForm.event.id, value })
            } else {
              createEvent.mutate(value)
            }
          }}
        />
      ) : null}
    </>
  )
}
