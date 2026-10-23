import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '@/api'
import { taskRequest } from '@/outbox/adapters'
import { barrier, visibleCommands } from '@/outbox/core'
import { projectTasks } from '@/outbox/projection'
import { TaskForm } from '@/TaskForm'
import { TrackerForm } from '@/TrackerForm'
import { EventForm } from '@/EventForm'
import { AnnotationForm } from '@/AnnotationForm'
import { useState, type ComponentProps } from 'react'
type Task = NonNullable<ComponentProps<typeof TaskForm>['initial']>
import type { Tracker, TrackerGroup } from '@/tracker-ui'
import type { CalendarEvent } from '@/calendar-ui'
import type { DayAnnotation } from '@/calendar-scroll'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'
import { reminderKey, type ReminderSource } from '@/reminder-ui'
import { ensurePushSubscription } from '@/push-subscription'

export function ReminderSourceDialog({ kind, sourceId, onClose }: { kind: ReminderSource; sourceId: string; onClose: () => void }) {
  const client = useQueryClient()
  const [openedAt] = useState(Date.now)
  const path = kind === 'task' ? `/api/tasks/${sourceId}` : kind === 'tracker'
    ? `/api/tracker/trackers/${sourceId}` : kind === 'annotation'
      ? `/api/reminders/annotation-detail/${sourceId}` : `/api/reminders/event-detail/${sourceId}`
  const source = useQuery({ queryKey: [...reminderKey, 'detail', kind, sourceId],
    queryFn: ({ signal }) => apiRequest<Task | Tracker | CalendarEvent | DayAnnotation>(path, { signal }),
    ...NO_POLLING_QUERY_OPTIONS, refetchOnMount: 'always' })
  const groups = useQuery({ queryKey: [...reminderKey, 'groups'], enabled: kind === 'tracker',
    queryFn: ({ signal }) => apiRequest<{ items: TrackerGroup[] }>('/api/tracker/groups', { signal }), ...NO_POLLING_QUERY_OPTIONS })
  const save = useMutation({ networkMode: kind === 'task' ? 'always' : 'online', mutationFn: async (body: object) => {
    const { ensure_push: ensurePush, ...payload } = body as { ensure_push?: boolean }
    if (kind === 'task') return taskRequest(path,{method:'PATCH',body:JSON.stringify(payload)})
    if (kind === 'tracker') await barrier('tracker:'+sourceId)
    if (kind === 'tracker' && ensurePush) await ensurePushSubscription()
    return apiRequest(kind === 'event' ? `/api/calendar/events/${sourceId}` : kind === 'annotation'
      ? `/api/calendar/annotations/${sourceId}` : path,
      { method: 'PATCH', body: JSON.stringify(payload) })
    }, onSuccess: () => {
      void Promise.all([reminderKey, ['tasks'], ['calendar'], ['tracker'], ['subscription']].map((queryKey) => client.invalidateQueries({ queryKey })))
      onClose()
    } })
  return <Dialog open onOpenChange={(v) => { if (!v) onClose() }}>
    <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-xl"><DialogHeader>
      <DialogTitle>Đối tượng được nhắc</DialogTitle><DialogDescription>Thay đổi mốc thời gian sẽ cập nhật lời nhắc đang chờ.</DialogDescription>
    </DialogHeader>
      {/* Forms initialize a draft once. On each opening, fetch the current source before
          mounting them; later background refetches must not replace an unsaved draft. */}
      {source.isPending || !source.isFetchedAfterMount ? <p role="status">Đang tải…</p> : source.isError ? <p role="alert">Đối tượng không còn hiển thị hoặc chưa tải được.</p> : <>
        {save.isError && <p role="alert" className="text-bad">{save.error.message}</p>}
        {kind === 'task' && <TaskSourceEditor initial={source.data as Task} pending={save.isPending} onSubmit={(v) => save.mutate(v)} onCancel={onClose} />}
        {kind === 'event' && <EventForm initial={source.data as CalendarEvent} manualSources={[]} pending={save.isPending} onSubmit={(v) => save.mutate(v)} onCancel={onClose} />}
        {kind === 'annotation' && <AnnotationForm initial={source.data as DayAnnotation} privateLocked={!(Date.parse(client.getQueryData<{ private_until: string | null }>(['session'])?.private_until ?? '') > openedAt)} pending={save.isPending} onSubmit={(v) => save.mutate(v)} onCancel={onClose} />}
        {kind === 'tracker' && (groups.isPending ? <p role="status">Đang tải nhóm…</p> : groups.isError ? <p role="alert">Chưa tải được nhóm tracker.</p>
          : <TrackerForm initial={source.data as Tracker} groups={groups.data.items} privateLocked={!(Date.parse(client.getQueryData<{ private_until: string | null }>(['session'])?.private_until ?? '') > openedAt)} pending={save.isPending} onSubmit={(v) => save.mutate(v)} onCancel={onClose} />)}
      </>}
    </DialogContent>
  </Dialog>
}


function TaskSourceEditor({initial,pending,onSubmit,onCancel}:{
  initial:Task;pending:boolean;onSubmit:(value:object)=>void;onCancel:()=>void
}) {
  // Capture the opened draft once; a later refetch never changes its comparison base.
  const [base] = useState(() => projectTasks([initial],visibleCommands())[0] ?? initial)
  return <TaskForm initial={base} pending={pending} submitLabel="Lưu task" onCancel={onCancel}
    onSubmit={value => {
      const patch:Record<string,unknown> = {}
      for(const [key,next] of Object.entries(value))
        if(JSON.stringify(next)!==JSON.stringify((base as unknown as Record<string,unknown>)[key]))patch[key]=next
      if(['due_precision','due_on','due_at'].some(key => key in patch))
        Object.assign(patch,{due_precision:value.due_precision,due_on:value.due_on,due_at:value.due_at})
      onSubmit(patch)
    }} />
}
