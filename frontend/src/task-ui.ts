/** Pure task-form state rules kept testable without a browser runtime. */

export type TaskStatus = 'open' | 'completed'
export type TaskFilter = TaskStatus | 'all'
export type TaskPriority = 'p1' | 'p2' | 'p3'

export type TaskFormState = {
  title: string
  body: string
  priority: TaskPriority | ''
  dueAt: string
  isPrivate: boolean
}

export type TaskWritePayload = {
  title: string
  body_md: string | null
  priority: TaskPriority | null
  due_at: string | null
  is_private: boolean
}

export type TaskPayload = TaskWritePayload & {
  id: string
}

export const taskInvalidationKey = ['tasks'] as const

export function taskQueryKey(filter: TaskFilter) {
  return ['tasks', filter] as const
}

export function taskPayload(state: TaskFormState): TaskWritePayload {
  return {
    title: state.title,
    body_md: state.body || null,
    priority: state.priority || null,
    due_at: state.dueAt ? new Date(state.dueAt).toISOString() : null,
    is_private: state.isPrivate,
  }
}

export function canSubmitTask(title: string, pending: boolean): boolean {
  return title.length > 0 && !pending
}

export function toggledStatus(completed: boolean): TaskStatus {
  return completed ? 'completed' : 'open'
}
