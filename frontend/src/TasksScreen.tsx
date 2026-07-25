import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, apiRequest, UnauthenticatedError } from '@/api'
import { Button } from '@/components/ui/button'
import { TaskForm } from '@/TaskForm'
import {
  type TaskFilter,
  type TaskPayload,
  type TaskPriority,
  type TaskStatus,
  taskInvalidationKey,
  taskQueryKey,
  toggledStatus,
} from '@/task-ui'

type TaskItem = {
  id: string
  content: string
  is_completed: boolean
  position: number
}

type Task = {
  id: string
  title: string
  body_md: string | null
  status: TaskStatus
  priority: TaskPriority | null
  due_at: string | null
  is_private: boolean
  items: TaskItem[]
}

const inputClass =
  'h-9 w-full rounded-md border bg-white px-3 text-sm outline-none focus:border-neutral-500'

function errorMessage(error: unknown): string {
  if (error instanceof UnauthenticatedError) return 'Phiên đã hết hạn. Tải lại để đăng nhập.'
  if (error instanceof ApiError) return error.message
  return 'Không kết nối được API.'
}

function TaskCard({ task }: { task: Task }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [newItem, setNewItem] = useState('')

  const refresh = () => queryClient.invalidateQueries({ queryKey: taskInvalidationKey })
  const update = useMutation({
    mutationFn: (payload: Partial<TaskPayload> & { status?: TaskStatus }) =>
      apiRequest<Task>(`/api/tasks/${task.id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => {
      setEditing(false)
      await refresh()
    },
  })
  const remove = useMutation({
    mutationFn: () => apiRequest<void>(`/api/tasks/${task.id}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })
  const addItem = useMutation({
    mutationFn: (content: string) =>
      apiRequest<TaskItem>(`/api/tasks/${task.id}/items`, {
        method: 'POST',
        body: JSON.stringify({ content, position: task.items.length }),
      }),
    onSuccess: async () => {
      setNewItem('')
      await refresh()
    },
  })
  const changeItem = useMutation({
    mutationFn: ({ item, isCompleted }: { item: TaskItem; isCompleted: boolean }) =>
      apiRequest<TaskItem>(`/api/tasks/${task.id}/items/${item.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_completed: isCompleted }),
      }),
    onSuccess: refresh,
  })
  const removeItem = useMutation({
    mutationFn: (item: TaskItem) =>
      apiRequest<void>(`/api/tasks/${task.id}/items/${item.id}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })
  const mutationError =
    update.error ?? remove.error ?? addItem.error ?? changeItem.error ?? removeItem.error

  if (editing) {
    return (
      <article className="rounded-lg border bg-white p-4 shadow-sm">
        <TaskForm
          initial={task}
          submitLabel="Lưu thay đổi"
          pending={update.isPending}
          onSubmit={(payload) => update.mutate(payload)}
          onCancel={() => setEditing(false)}
        />
        {update.isError ? (
          <p className="mt-3 text-sm text-red-700">{errorMessage(update.error)}</p>
        ) : null}
      </article>
    )
  }

  return (
    <article className="space-y-3 rounded-lg border bg-white p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <input
          aria-label={`Đánh dấu ${task.title} hoàn thành`}
          className="mt-1"
          type="checkbox"
          checked={task.status === 'completed'}
          disabled={update.isPending}
          onChange={(event) =>
            update.mutate({ status: toggledStatus(event.target.checked) })
          }
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3
              className={
                task.status === 'completed'
                  ? 'font-medium text-neutral-500 line-through'
                  : 'font-medium'
              }
            >
              {task.title}
            </h3>
            {task.priority ? (
              <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-xs uppercase">
                {task.priority}
              </span>
            ) : null}
            {task.is_private ? (
              <span className="rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-800">
                Riêng tư
              </span>
            ) : null}
          </div>
          {task.body_md ? (
            <p className="mt-1 whitespace-pre-wrap text-sm text-neutral-600">{task.body_md}</p>
          ) : null}
          {task.due_at ? (
            <p className="mt-1 text-xs text-neutral-500">
              Hạn {new Date(task.due_at).toLocaleString('vi-VN')}
            </p>
          ) : null}
        </div>
        <div className="flex gap-1">
          <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
            Sửa
          </Button>
          <Button
            size="sm"
            variant="destructive"
            disabled={remove.isPending}
            onClick={() => remove.mutate()}
          >
            Xoá
          </Button>
        </div>
      </div>

      <div className="space-y-2 border-t pt-3">
        {task.items.map((item) => (
          <div className="flex items-center gap-2 text-sm" key={item.id}>
            <input
              aria-label={`Đánh dấu ${item.content} hoàn thành`}
              type="checkbox"
              checked={item.is_completed}
              disabled={changeItem.isPending}
              onChange={(event) =>
                changeItem.mutate({ item, isCompleted: event.target.checked })
              }
            />
            <span className={item.is_completed ? 'flex-1 text-neutral-500 line-through' : 'flex-1'}>
              {item.content}
            </span>
            <Button
              size="xs"
              variant="ghost"
              disabled={removeItem.isPending}
              onClick={() => removeItem.mutate(item)}
            >
              Xoá
            </Button>
          </div>
        ))}
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (newItem) addItem.mutate(newItem)
          }}
        >
          <input
            aria-label={`Thêm checklist cho ${task.title}`}
            className={inputClass}
            placeholder="Thêm checklist…"
            value={newItem}
            onChange={(event) => setNewItem(event.target.value)}
          />
          <Button type="submit" variant="secondary" disabled={!newItem || addItem.isPending}>
            Thêm
          </Button>
        </form>
      </div>

      {mutationError ? (
        <p className="text-sm text-red-700">{errorMessage(mutationError)}</p>
      ) : null}
    </article>
  )
}

export function TasksScreen() {
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState<TaskFilter>('open')
  const tasks = useQuery({
    queryKey: taskQueryKey(filter),
    queryFn: () =>
      apiRequest<{ items: Task[] }>(
        `/api/tasks?status=${filter}&limit=100&offset=0`,
      ),
    retry: (failureCount, error) =>
      !(error instanceof UnauthenticatedError) && failureCount < 2,
  })
  const create = useMutation({
    mutationFn: (payload: TaskPayload) =>
      apiRequest<Task>('/api/tasks', {
        method: 'POST',
        body: JSON.stringify({ ...payload, items: [] }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: taskInvalidationKey }),
  })

  return (
    <div className="space-y-6">
      <section className="rounded-lg border bg-white p-4 shadow-sm">
        <h2 className="mb-3 text-lg font-medium">Tạo task</h2>
        <TaskForm
          submitLabel="Tạo task"
          pending={create.isPending}
          onSubmit={(payload) => create.mutate(payload)}
        />
        {create.isError ? (
          <p className="mt-3 text-sm text-red-700">{errorMessage(create.error)}</p>
        ) : null}
        <p className="mt-3 text-xs text-neutral-500">
          Task riêng tư sẽ được mã hoá và ẩn cho tới khi private unlock được mở.
        </p>
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-medium">Danh sách</h2>
          <label className="flex items-center gap-2 text-sm">
            <span>Trạng thái</span>
            <select
              className={inputClass}
              value={filter}
              onChange={(event) => setFilter(event.target.value as TaskFilter)}
            >
              <option value="open">Đang mở</option>
              <option value="completed">Đã xong</option>
              <option value="all">Tất cả</option>
            </select>
          </label>
        </div>

        {tasks.isPending ? <p className="text-sm text-neutral-600">Đang tải task…</p> : null}
        {tasks.isError ? (
          <div className="flex items-center gap-3">
            <p className="text-sm text-red-700">{errorMessage(tasks.error)}</p>
            <Button variant="outline" size="sm" onClick={() => void tasks.refetch()}>
              Thử lại
            </Button>
          </div>
        ) : null}
        {tasks.data?.items.length === 0 ? (
          <p className="rounded-lg border border-dashed p-6 text-center text-sm text-neutral-500">
            Chưa có task trong trạng thái này.
          </p>
        ) : null}
        {tasks.data?.items.map((task) => <TaskCard task={task} key={task.id} />)}
      </section>
    </div>
  )
}
