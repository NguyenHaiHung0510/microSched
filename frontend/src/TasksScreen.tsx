import {
  type FormEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Edit3,
  LockKeyhole,
  Pin,
  PinOff,
  Plus,
  Trash2,
} from 'lucide-react'

import { ApiError, apiRequest, TimeoutError, UnauthenticatedError } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
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

type CreateSource = 'quick' | 'detail'

const PINNED_STORAGE_KEY = 'microsched:pinned-task-ids'

const priorityLabels: Record<TaskPriority, string> = {
  p1: 'P1',
  p2: 'P2',
  p3: 'P3',
}

const filterLabels: Record<TaskFilter, string> = {
  open: 'Đang mở',
  completed: 'Đã xong',
  all: 'Tất cả',
}

function errorMessage(error: unknown): string {
  if (error instanceof UnauthenticatedError) return 'Phiên đã hết hạn. Tải lại để đăng nhập.'
  if (error instanceof TimeoutError) return error.message
  if (error instanceof ApiError) return error.message
  return 'Không kết nối được API.'
}

function loadPinnedIds(): Set<string> {
  if (typeof window === 'undefined') return new Set()

  try {
    const stored = JSON.parse(window.localStorage.getItem(PINNED_STORAGE_KEY) ?? '[]')
    return new Set(
      Array.isArray(stored)
        ? stored.filter((value): value is string => typeof value === 'string')
        : [],
    )
  } catch {
    return new Set()
  }
}

function formatDue(value: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function isOverdue(task: Task): boolean {
  return (
    task.status === 'open' &&
    task.due_at !== null &&
    new Date(task.due_at).getTime() < Date.now()
  )
}

function PriorityBadge({ priority }: { priority: TaskPriority }) {
  if (priority === 'p1') {
    return <Badge>{priorityLabels[priority]}</Badge>
  }

  return (
    <Badge variant={priority === 'p2' ? 'secondary' : 'outline'}>
      {priorityLabels[priority]}
    </Badge>
  )
}

function TaskCard({
  task,
  pinned,
  onTogglePin,
  onRemoved,
}: {
  task: Task
  pinned: boolean
  onTogglePin: () => void
  onRemoved: () => void
}) {
  const queryClient = useQueryClient()
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [newItem, setNewItem] = useState('')

  /* `void`, không `await`: React Query giữ mutation ở `isPending` cho tới khi
     `onSuccess` resolve, mà `invalidateQueries` thì đợi luôn cả lượt tải lại.
     Await ở đây nghĩa là nút vẫn ghi "Đang thêm…" DÙ việc đã lưu xong — và nếu
     lượt tải lại treo thì nút treo theo vĩnh viễn. Ghi xong là ghi xong. */
  const refresh = () => void queryClient.invalidateQueries({ queryKey: taskInvalidationKey })
  const update = useMutation({
    mutationFn: (payload: Partial<TaskPayload> & { status?: TaskStatus }) =>
      apiRequest<Task>(`/api/tasks/${task.id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      setEditing(false)
      refresh()
    },
  })
  const remove = useMutation({
    mutationFn: () => apiRequest<void>(`/api/tasks/${task.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      setDetailsOpen(false)
      onRemoved()
      refresh()
    },
  })
  const addItem = useMutation({
    mutationFn: (content: string) =>
      apiRequest<TaskItem>(`/api/tasks/${task.id}/items`, {
        method: 'POST',
        body: JSON.stringify({ content, position: task.items.length }),
      }),
    onSuccess: () => {
      setNewItem('')
      refresh()
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

  const completedItems = task.items.filter((item) => item.is_completed).length
  const visibleItems = expanded ? task.items : task.items.slice(0, 3)
  const hiddenItems = Math.max(0, task.items.length - 3)
  const mutationError =
    update.error ?? remove.error ?? addItem.error ?? changeItem.error ?? removeItem.error

  function openDetails() {
    setEditing(false)
    setDetailsOpen(true)
  }

  function openEditor() {
    setEditing(true)
    setDetailsOpen(true)
  }

  return (
    <>
      <Card
        className={[
          'group/task relative gap-3 overflow-visible rounded-lg px-4 py-4 shadow-2 ring-0 transition-shadow',
          pinned ? 'bg-brand-50 shadow-rose' : 'bg-card',
          task.status === 'completed' ? 'opacity-70' : '',
        ].join(' ')}
      >
        <div className="flex items-start gap-3">
          <Checkbox
            className="mt-1 size-5 rounded-md"
            aria-label={`Đánh dấu ${task.title} hoàn thành`}
            checked={task.status === 'completed'}
            disabled={update.isPending}
            onCheckedChange={(checked) =>
              update.mutate({ status: toggledStatus(checked === true) })
            }
          />

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              {/* rose-500 trên nền thẻ ghim (rose-50) chỉ đạt 2,82:1, dưới ngưỡng
                  3:1 của non-text contrast. Dùng `--primary` (rose-700, 5,29:1)
                  — vẫn là màu nhận diện, chỉ đậm hơn. */}
              {pinned ? <Pin className="size-4 text-primary" aria-hidden="true" /> : null}
              <Button
                className={[
                  'h-auto min-w-0 justify-start whitespace-normal p-0 text-left text-base font-bold tracking-tight hover:bg-transparent',
                  task.status === 'completed' ? 'line-through' : '',
                ].join(' ')}
                variant="ghost"
                aria-label={`Mở chi tiết ${task.title}`}
                onClick={openDetails}
              >
                {task.title}
              </Button>
              {task.priority ? <PriorityBadge priority={task.priority} /> : null}
              {task.is_private ? (
                <Badge variant="secondary">
                  <LockKeyhole data-icon="inline-start" />
                  Riêng tư
                </Badge>
              ) : null}
            </div>

            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
              {task.due_at ? (
                <span className={isOverdue(task) ? 'font-bold text-bad' : ''}>
                  {isOverdue(task) ? 'Trễ · ' : 'Hạn '}
                  {formatDue(task.due_at)}
                </span>
              ) : (
                <span>Không hạn</span>
              )}
              {task.items.length > 0 ? (
                <span className="tabular-nums">
                  {completedItems}/{task.items.length} mục nhỏ
                </span>
              ) : null}
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap justify-end gap-2">
            <Button
              size="icon-lg"
              variant="ghost"
              aria-label={pinned ? `Bỏ ghim ${task.title}` : `Ghim ${task.title}`}
              onClick={onTogglePin}
            >
              {pinned ? <PinOff /> : <Pin />}
            </Button>
            <Button
              size="icon-lg"
              variant="ghost"
              aria-label={`Sửa ${task.title}`}
              onClick={openEditor}
            >
              <Edit3 />
            </Button>
            <Button
              size="icon-lg"
              variant="ghost"
              className="text-bad hover:text-bad"
              aria-label={`Xoá ${task.title}`}
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
            >
              <Trash2 />
            </Button>
          </div>
        </div>

        {task.items.length > 0 ? (
          <div className="ml-8 space-y-2">
            {visibleItems.map((item) => (
              <label
                className="flex min-h-8 items-center gap-3 text-sm text-foreground"
                key={item.id}
              >
                <Checkbox
                  aria-label={`Đánh dấu ${item.content} hoàn thành`}
                  checked={item.is_completed}
                  disabled={changeItem.isPending}
                  onCheckedChange={(checked) =>
                    changeItem.mutate({ item, isCompleted: checked === true })
                  }
                />
                <span
                  className={
                    item.is_completed ? 'text-muted-foreground line-through' : ''
                  }
                >
                  {item.content}
                </span>
              </label>
            ))}

            {hiddenItems > 0 ? (
              <Button
                className="h-auto px-0 py-1 text-xs"
                size="sm"
                variant="link"
                onClick={() => setExpanded((current) => !current)}
              >
                {expanded ? (
                  <>
                    <ChevronUp data-icon="inline-start" />
                    Thu gọn
                  </>
                ) : (
                  <>
                    <ChevronDown data-icon="inline-start" />+ {hiddenItems} mục khác…
                  </>
                )}
              </Button>
            ) : null}
          </div>
        ) : null}

        {mutationError ? (
          <p className="ml-8 text-sm text-bad">{errorMessage(mutationError)}</p>
        ) : null}

        {task.body_md || task.items.length > 0 ? (
          <div
            className="pointer-events-none absolute top-[calc(100%-0.25rem)] right-4 left-4 z-10 hidden translate-y-1 rounded-md bg-tooltip px-4 py-3 text-xs leading-relaxed text-tooltip-foreground opacity-0 shadow-3 transition-all group-hover/task:translate-y-0 group-hover/task:opacity-100 md:block"
            aria-hidden="true"
          >
            {task.items.length > 0 ? (
              <p>
                <span className="font-bold">Checklist · </span>
                {task.items.map((item) => item.content).join(' · ')}
              </p>
            ) : null}
            {task.body_md ? (
              <p className={task.items.length > 0 ? 'mt-2' : ''}>
                <span className="font-bold">Ghi chú · </span>
                {task.body_md}
              </p>
            ) : null}
          </div>
        ) : null}
      </Card>

      <Dialog
        open={detailsOpen}
        onOpenChange={(open) => {
          setDetailsOpen(open)
          if (!open) setEditing(false)
        }}
      >
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing ? `Sửa · ${task.title}` : task.title}</DialogTitle>
            <DialogDescription>
              {editing
                ? 'Cập nhật nội dung, ưu tiên, hạn hoặc chế độ riêng tư.'
                : 'Chi tiết task và checklist.'}
            </DialogDescription>
          </DialogHeader>

          {editing ? (
            <TaskForm
              initial={task}
              submitLabel="Lưu thay đổi"
              pending={update.isPending}
              onSubmit={(payload) => update.mutate(payload)}
              onCancel={() => setEditing(false)}
            />
          ) : (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-2">
                {task.priority ? <PriorityBadge priority={task.priority} /> : null}
                {task.is_private ? (
                  <Badge variant="secondary">
                    <LockKeyhole data-icon="inline-start" />
                    Riêng tư
                  </Badge>
                ) : null}
                <Badge variant={task.status === 'completed' ? 'secondary' : 'outline'}>
                  {task.status === 'completed' ? 'Đã xong' : 'Đang mở'}
                </Badge>
              </div>

              <div className="space-y-1">
                <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Hạn
                </p>
                <p className={task.due_at && isOverdue(task) ? 'font-bold text-bad' : ''}>
                  {task.due_at ? formatDue(task.due_at) : 'Không đặt hạn'}
                </p>
              </div>

              <div className="space-y-1">
                <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Ghi chú
                </p>
                <p className="whitespace-pre-wrap text-sm">
                  {task.body_md || 'Chưa có ghi chú.'}
                </p>
              </div>

              <div className="space-y-3">
                <div>
                  <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Checklist
                  </p>
                  {task.items.length > 0 ? (
                    <p className="mt-1 text-xs text-muted-foreground">
                      {completedItems}/{task.items.length} mục đã xong
                    </p>
                  ) : null}
                </div>

                {task.items.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Chưa có mục nhỏ.</p>
                ) : (
                  <div className="space-y-2">
                    {task.items.map((item) => (
                      <div className="flex min-h-9 items-center gap-3" key={item.id}>
                        <Checkbox
                          aria-label={`Đánh dấu ${item.content} hoàn thành`}
                          checked={item.is_completed}
                          disabled={changeItem.isPending}
                          onCheckedChange={(checked) =>
                            changeItem.mutate({ item, isCompleted: checked === true })
                          }
                        />
                        <span
                          className={[
                            'min-w-0 flex-1 text-sm',
                            item.is_completed
                              ? 'text-muted-foreground line-through'
                              : '',
                          ].join(' ')}
                        >
                          {item.content}
                        </span>
                        <Button
                          size="icon-lg"
                          variant="ghost"
                          className="text-bad hover:text-bad"
                          aria-label={`Xoá mục ${item.content}`}
                          disabled={removeItem.isPending}
                          onClick={() => removeItem.mutate(item)}
                        >
                          <Trash2 />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}

                <form
                  className="flex gap-2"
                  onSubmit={(event) => {
                    event.preventDefault()
                    const content = newItem.trim()
                    if (content) addItem.mutate(content)
                  }}
                >
                  <Input
                    aria-label={`Thêm checklist cho ${task.title}`}
                    className="h-10 bg-card"
                    placeholder="Thêm checklist…"
                    value={newItem}
                    onChange={(event) => setNewItem(event.target.value)}
                  />
                  <Button
                    size="lg"
                    type="submit"
                    variant="secondary"
                    disabled={!newItem.trim() || addItem.isPending}
                  >
                    <Plus data-icon="inline-start" />
                    Thêm
                  </Button>
                </form>
              </div>

              <div className="flex flex-wrap gap-2 border-t pt-4">
                <Button size="lg" onClick={() => setEditing(true)}>
                  <Edit3 data-icon="inline-start" />
                  Sửa task
                </Button>
                <Button
                  size="lg"
                  variant="destructive"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate()}
                >
                  <Trash2 data-icon="inline-start" />
                  {remove.isPending ? 'Đang xoá…' : 'Xoá'}
                </Button>
              </div>
            </div>
          )}

          {mutationError ? (
            <p className="text-sm text-bad">{errorMessage(mutationError)}</p>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  )
}

export function TasksScreen() {
  const queryClient = useQueryClient()
  const quickInputRef = useRef<HTMLInputElement>(null)
  const [filter, setFilter] = useState<TaskFilter>('open')
  const [quickTitle, setQuickTitle] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [pinnedIds, setPinnedIds] = useState<Set<string>>(loadPinnedIds)

  useEffect(() => {
    try {
      window.localStorage.setItem(PINNED_STORAGE_KEY, JSON.stringify([...pinnedIds]))
    } catch {
      // Pinning is a best-effort client preference until it gets a database column.
    }
  }, [pinnedIds])

  const tasks = useQuery({
    queryKey: taskQueryKey('all'),
    queryFn: () =>
      apiRequest<{ items: Task[] }>('/api/tasks?status=all&limit=100&offset=0'),
    retry: (failureCount, error) =>
      !(error instanceof UnauthenticatedError) && failureCount < 2,
  })
  const create = useMutation({
    mutationFn: ({ payload }: { payload: TaskPayload; source: CreateSource }) =>
      apiRequest<Task>('/api/tasks', {
        method: 'POST',
        body: JSON.stringify({ ...payload, items: [] }),
      }),
    onSuccess: async (_task, variables) => {
      await queryClient.invalidateQueries({ queryKey: taskInvalidationKey })

      if (variables.source === 'quick') {
        setQuickTitle('')
        window.requestAnimationFrame(() => quickInputRef.current?.focus())
      } else {
        setCreateOpen(false)
      }
    },
  })

  const overdueCount = useMemo(
    () => tasks.data?.items.filter(isOverdue).length ?? 0,
    [tasks.data?.items],
  )

  const visibleTasks = useMemo(() => {
    const items = tasks.data?.items ?? []

    return items
      .filter(
        (task) =>
          pinnedIds.has(task.id) || filter === 'all' || task.status === filter,
      )
      .sort((left, right) => {
        const pinOrder =
          Number(pinnedIds.has(right.id)) - Number(pinnedIds.has(left.id))
        if (pinOrder !== 0) return pinOrder

        const leftDue = left.due_at ? new Date(left.due_at).getTime() : Infinity
        const rightDue = right.due_at ? new Date(right.due_at).getTime() : Infinity
        if (leftDue !== rightDue) return leftDue - rightDue

        return left.title.localeCompare(right.title, 'vi')
      })
  }, [filter, pinnedIds, tasks.data?.items])

  function togglePinned(taskId: string) {
    setPinnedIds((current) => {
      const next = new Set(current)
      if (next.has(taskId)) next.delete(taskId)
      else next.add(taskId)
      return next
    })
  }

  function forgetPinned(taskId: string) {
    setPinnedIds((current) => {
      if (!current.has(taskId)) return current
      const next = new Set(current)
      next.delete(taskId)
      return next
    })
  }

  function quickAdd(event: FormEvent) {
    event.preventDefault()
    const title = quickTitle.trim()
    if (!title || create.isPending) return

    create.mutate({
      source: 'quick',
      payload: {
        title,
        body_md: null,
        priority: null,
        due_at: null,
        is_private: false,
      },
    })
  }

  return (
    <div className="space-y-4">
      {overdueCount > 0 ? (
        <div
          className="flex items-center gap-3 rounded-lg bg-bad-bg px-4 py-3 text-sm font-bold text-bad"
          role="status"
        >
          <AlertTriangle className="size-5 shrink-0" aria-hidden="true" />
          {/* Tiếng Việt không đổi dạng số nhiều — đừng thêm nhánh đếm ở đây. */}
          <span>{overdueCount} việc trễ hạn</span>
        </div>
      ) : null}

      <section aria-labelledby="quick-add-heading">
        <h2 className="sr-only" id="quick-add-heading">
          Thêm task
        </h2>
        <form className="flex gap-2" onSubmit={quickAdd}>
          <Input
            ref={quickInputRef}
            className="h-11 flex-1 rounded-lg bg-card px-4 shadow-1"
            aria-label="Thêm task nhanh"
            placeholder="Thêm việc rồi lưu…"
            value={quickTitle}
            onChange={(event) => setQuickTitle(event.target.value)}
          />
          <Button
            className="h-11 rounded-lg px-5"
            size="lg"
            type="submit"
            disabled={!quickTitle.trim() || create.isPending}
          >
            {create.isPending ? 'Đang thêm…' : 'Thêm'}
          </Button>
        </form>

        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 px-1">
          <p className="text-xs text-muted-foreground">
            Lưu xong ô tự xoá và giữ con trỏ để gõ tiếp.
          </p>
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button className="h-auto px-0 py-1 text-xs" size="sm" variant="link">
                <Plus data-icon="inline-start" />
                Thêm đủ chi tiết
              </Button>
            </DialogTrigger>
            <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>Tạo task</DialogTitle>
                <DialogDescription>
                  Thêm ghi chú, ưu tiên, hạn hoặc chế độ riêng tư.
                </DialogDescription>
              </DialogHeader>
              <TaskForm
                submitLabel="Tạo task"
                pending={create.isPending}
                onSubmit={(payload) => create.mutate({ payload, source: 'detail' })}
                onCancel={() => setCreateOpen(false)}
              />
              {create.isError ? (
                <p className="text-sm text-bad">{errorMessage(create.error)}</p>
              ) : null}
              <p className="text-xs text-muted-foreground">
                Task riêng tư sẽ được mã hoá và ẩn cho tới khi private unlock được mở.
              </p>
            </DialogContent>
          </Dialog>
        </div>
      </section>

      <section aria-labelledby="task-list-heading" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="sr-only" id="task-list-heading">
            Danh sách task
          </h2>
          <div className="flex flex-wrap gap-1" role="group" aria-label="Lọc task">
            {(Object.keys(filterLabels) as TaskFilter[]).map((value) => (
              <Button
                className="rounded-full px-4"
                size="lg"
                variant={filter === value ? 'secondary' : 'ghost'}
                aria-pressed={filter === value}
                key={value}
                onClick={() => setFilter(value)}
              >
                {filterLabels[value]}
              </Button>
            ))}
          </div>
        </div>

        {tasks.isPending ? (
          <p className="text-sm text-muted-foreground">Đang tải task…</p>
        ) : null}
        {tasks.isError ? (
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-sm text-bad">{errorMessage(tasks.error)}</p>
            <Button variant="outline" size="lg" onClick={() => void tasks.refetch()}>
              Thử lại
            </Button>
          </div>
        ) : null}
        {tasks.data && visibleTasks.length === 0 ? (
          <Card className="rounded-lg border border-dashed bg-transparent p-6 text-center text-sm text-muted-foreground shadow-none">
            Chưa có task trong trạng thái này.
          </Card>
        ) : null}

        <div className="space-y-3">
          {visibleTasks.map((task) => (
            <TaskCard
              task={task}
              pinned={pinnedIds.has(task.id)}
              onTogglePin={() => togglePinned(task.id)}
              onRemoved={() => forgetPinned(task.id)}
              key={task.id}
            />
          ))}
        </div>
      </section>
    </div>
  )
}
