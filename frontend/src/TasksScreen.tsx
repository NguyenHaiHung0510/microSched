import {
  type FormEvent,
  type MouseEvent,
  memo,
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
import { toast } from 'sonner'

import { ApiError, apiRequest, UnauthenticatedError } from '@/api'
import { endOfDayVietnam } from '@/calendar-scroll'
import { addVietnamDays, todayInVietnam, VIETNAM_TIME_ZONE } from '@/calendar-ui'
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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { uuidv7 } from '@/lib/uuidv7'
import { taskRefetchInterval } from '@/query-polling'
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
import { errorMessage, restoreTask } from '@/task-undo'

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
  pinned: boolean
  items: TaskItem[]
  created_at?: string | null
  updated_at?: string | null
}

type CursorRangeState = {
  from: string
  to: string
  cursors: Record<TimelineBucket, string | null>
}

function cursorRangeKey(from: string, to: string): string {
  return `${from}|${to}`
}

function emptyBucketCursors(): Record<TimelineBucket, string | null> {
  return { overdue: null, dated: null, undated: null }
}

function formatTimelineDay(day: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: VIETNAM_TIME_ZONE,
    weekday: 'long',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(`${day}T00:00:00+07:00`))
}

function sortTimelineTasks(tasks: Task[]): Task[] {
  return [...tasks].sort((left, right) => {
    if (left.pinned !== right.pinned) return left.pinned ? -1 : 1
    if (left.due_at && right.due_at) {
      const due = Date.parse(left.due_at) - Date.parse(right.due_at)
      if (due !== 0) return due
    } else if (left.due_at) return -1
    else if (right.due_at) return 1
    const created = Date.parse(right.created_at ?? '') - Date.parse(left.created_at ?? '')
    return created || left.id.localeCompare(right.id)
  })
}

export function TasksScreen() {
  const queryClient = useQueryClient()
  const quickInputRef = useRef<HTMLInputElement>(null)
  const overdueRef = useRef<HTMLDivElement>(null)
  const [filter, setFilter] = useState<ListView>('open')
  const [quickTitle, setQuickTitle] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [migratingPins, setMigratingPins] = useState(false)
  const today = todayInVietnam()
  const defaultStart = addVietnamDays(today, -3)
  const defaultEnd = addVietnamDays(today, 3)
  const [loadedStart, setLoadedStart] = useState(defaultStart)
  const [loadedEnd, setLoadedEnd] = useState(defaultEnd)
  const [extraTasks, setExtraTasks] = useState<Task[]>([])
  const [bucketCursors, setBucketCursors] = useState<Record<TimelineBucket, string | null>>({
    overdue: null,
    dated: null,
    undated: null,
  })
  const [hasPrevious, setHasPrevious] = useState(false)
  const [hasNext, setHasNext] = useState(false)
  const [rangeError, setRangeError] = useState<{ direction: 'earlier' | 'later'; text: string } | null>(null)
  const [continuationError, setContinuationError] = useState<{ bucket: TimelineBucket; text: string } | null>(null)
  const [completedOpen, setCompletedOpen] = useState<Set<string>>(new Set())
  const [loadingDirection, setLoadingDirection] = useState<'earlier' | 'later' | null>(null)
  const [continuationLoading, setContinuationLoading] = useState(false)
  const defaultCursorTo = addVietnamDays(defaultEnd, 1)
  const defaultRangeKey = cursorRangeKey(defaultStart, defaultCursorTo)
  const cursorRangesRef = useRef<Record<string, CursorRangeState>>({
    [defaultRangeKey]: { from: defaultStart, to: defaultCursorTo, cursors: emptyBucketCursors() },
  })
  const continuationRangeByBucketRef = useRef<Record<TimelineBucket, string>>({
    overdue: defaultRangeKey,
    dated: defaultRangeKey,
    undated: defaultRangeKey,
  })
  const cursorStoreSeededRef = useRef(false)

  useEffect(() => {
    queueMicrotask(() => {
      const nextRange = { from: defaultStart, to: addVietnamDays(defaultEnd, 1) }
      const nextRangeKey = cursorRangeKey(nextRange.from, nextRange.to)
      cursorRangesRef.current = {
        [nextRangeKey]: { ...nextRange, cursors: emptyBucketCursors() },
      }
      continuationRangeByBucketRef.current = {
        overdue: nextRangeKey,
        dated: nextRangeKey,
        undated: nextRangeKey,
      }
      cursorStoreSeededRef.current = false
      setLoadedStart(defaultStart)
      setLoadedEnd(defaultEnd)
      setExtraTasks([])
      setBucketCursors({ overdue: null, dated: null, undated: null })
      setHasPrevious(false)
      setHasNext(false)
      setRangeError(null)
      setContinuationError(null)
      setCompletedOpen(new Set())
    })
  }, [defaultEnd, defaultStart, filter])

  const timeline = useQuery({
    queryKey: ['tasks', 'timeline', filter, defaultStart, defaultEnd],
    queryFn: () =>
      apiRequest<TaskTimelineResponse>(
        `/api/tasks/timeline?status=${filter}&from=${encodeURIComponent(`${defaultStart}T00:00:00+07:00`)}&to=${encodeURIComponent(`${addVietnamDays(defaultEnd, 1)}T00:00:00+07:00`)}&limit=50`,
      ),
    refetchInterval: taskRefetchInterval,
    retry: (failureCount, error) =>
      !(error instanceof UnauthenticatedError) && failureCount < 2,
  })

  useEffect(() => {
    if (timeline.data && !cursorStoreSeededRef.current) {
      cursorStoreSeededRef.current = true
      queueMicrotask(() => {
        const cursors = {
          overdue: timeline.data.bucket_cursors.overdue ?? null,
          dated: timeline.data.bucket_cursors.dated ?? null,
          undated: timeline.data.bucket_cursors.undated ?? null,
        }
        cursorRangesRef.current[defaultRangeKey] = {
          from: defaultStart,
          to: defaultCursorTo,
          cursors,
        }
        continuationRangeByBucketRef.current = {
          overdue: defaultRangeKey,
          dated: defaultRangeKey,
          undated: defaultRangeKey,
        }
        setBucketCursors(cursors)
        setHasPrevious(timeline.data.has_previous)
        setHasNext(timeline.data.has_next)
      })
    }
  }, [defaultCursorTo, defaultEnd, defaultRangeKey, defaultStart, timeline.data])

  useEffect(() => {
    if (!timeline.isSuccess || !navigator.onLine) return
    let pinnedIds: string[]
    try {
      if (window.localStorage.getItem(PINNED_MIGRATED_KEY) === '1') return
      const stored = JSON.parse(window.localStorage.getItem(LEGACY_PIN_IDS_KEY) ?? '[]')
      pinnedIds = Array.isArray(stored)
        ? [...new Set(stored.filter((value): value is string => typeof value === 'string'))]
        : []
    } catch {
      return
    }
    if (pinnedIds.length === 0) return
    try {
      window.localStorage.setItem(PINNED_MIGRATED_KEY, '1')
    } catch {
      return
    }
    queueMicrotask(() => setMigratingPins(true))
    void Promise.allSettled(
      pinnedIds.map((taskId) =>
        apiRequest<Task>(`/api/tasks/${taskId}`, {
          method: 'PATCH',
          body: JSON.stringify({ pinned: true }),
        }),
      ),
    ).then((results) => {
      const retryIds = results.flatMap((result, index) =>
        result.status === 'rejected' ? [pinnedIds[index]] : [],
      )
      try {
        if (retryIds.length === 0) window.localStorage.removeItem(LEGACY_PIN_IDS_KEY)
        else window.localStorage.setItem(LEGACY_PIN_IDS_KEY, JSON.stringify(retryIds))
        if (retryIds.length > 0) window.localStorage.removeItem(PINNED_MIGRATED_KEY)
      } catch {
        // A blocked storage area must not make the task screen unusable.
      }
      void queryClient.invalidateQueries({ queryKey: taskInvalidationKey })
      setMigratingPins(false)
    })
  }, [queryClient, timeline.isSuccess])

  const create = useMutation({
    mutationFn: (payload: TaskPayload) =>
      apiRequest<Task>('/api/tasks', {
        method: 'POST',
        body: JSON.stringify({ ...payload, items: [] }),
      }),
    onSuccess: () => {
      setQuickTitle('')
      setCreateOpen(false)
      window.requestAnimationFrame(() => quickInputRef.current?.focus())
      void queryClient.invalidateQueries({ queryKey: taskInvalidationKey })
      void queryClient.invalidateQueries({ queryKey: ['calendar'] })
    },
  })

  const tasks = useMemo(() => {
    const seen = new Set<string>()
    return [...(timeline.data?.items ?? []), ...extraTasks].filter((task) => {
      if (seen.has(task.id)) return false
      seen.add(task.id)
      return true
    })
  }, [extraTasks, timeline.data?.items])

  const dateKeys = useMemo(() => {
    const keys: string[] = []
    for (let day = loadedStart; day <= loadedEnd; day = addVietnamDays(day, 1)) keys.push(day)
    return keys
  }, [loadedEnd, loadedStart])

  const groups = useMemo(() => {
    const dateGroups = new Map<string, Task[]>()
    dateKeys.forEach((day) => dateGroups.set(day, []))
    const overdue: Task[] = []
    const undated: Task[] = []
    for (const task of tasks) {
      if (task.due_at === null) {
        undated.push(task)
        continue
      }
      const key = vietnamDateKey(task.due_at)
      if (dateGroups.has(key)) dateGroups.get(key)?.push(task)
      else if (task.status === 'open' && key < loadedStart) overdue.push(task)
    }
    return {
      dateGroups: dateKeys.map((day) => ({ day, tasks: sortTimelineTasks(dateGroups.get(day) ?? []) })),
      overdue: sortTimelineTasks(overdue),
      undated: sortTimelineTasks(undated),
    }
  }, [dateKeys, loadedStart, tasks])

  async function loadBlock(direction: 'earlier' | 'later') {
    if (
      loadingDirection ||
      (direction === 'earlier' && !hasPrevious) ||
      (direction === 'later' && !hasNext)
    ) return
    const from = direction === 'earlier' ? addVietnamDays(loadedStart, -7) : addVietnamDays(loadedEnd, 1)
    const to = direction === 'earlier' ? loadedStart : addVietnamDays(loadedEnd, 8)
    setLoadingDirection(direction)
    setRangeError(null)
    setContinuationError(null)
    try {
      const response = await apiRequest<TaskTimelineResponse>(
        `/api/tasks/timeline?status=${filter}&from=${encodeURIComponent(`${from}T00:00:00+07:00`)}&to=${encodeURIComponent(`${to}T00:00:00+07:00`)}&limit=50`,
      )
      const terminal =
        response.items.length === 0 &&
        (direction === 'earlier' ? !response.has_previous : !response.has_next)
      if (terminal) {
        setRangeError({
          direction,
          text: direction === 'earlier' ? 'Đã tới đầu lịch sử có thể xem.' : 'Đã tới cuối lịch có thể xem.',
        })
        if (direction === 'earlier') setHasPrevious(false)
        else setHasNext(false)
        return
      }
      setExtraTasks((current) => [...current, ...response.items])
      if (direction === 'earlier') setLoadedStart(from)
      else setLoadedEnd(addVietnamDays(to, -1))
      const rangeKey = cursorRangeKey(from, to)
      const cursors = {
        overdue: null,
        dated: response.bucket_cursors.dated ?? null,
        undated: null,
      }
      cursorRangesRef.current[rangeKey] = { from, to, cursors }
      setBucketCursors((current) => {
        const next = { ...current }
        if (!next.dated) {
          const pendingRange = Object.entries(cursorRangesRef.current).find(
            ([, state]) => Boolean(state.cursors.dated),
          )
          if (pendingRange) {
            continuationRangeByBucketRef.current.dated = pendingRange[0]
            next.dated = pendingRange[1].cursors.dated
          }
        }
        return next
      })
      setHasPrevious(response.has_previous)
      setHasNext(response.has_next)
    } catch {
      setRangeError({ direction, text: 'Không tải được khoảng ngày. Thử lại.' })
    } finally {
      setLoadingDirection(null)
    }
  }

  async function loadMoreBucket(bucket: TimelineBucket) {
    const rangeKey = bucket === 'dated'
      ? continuationRangeByBucketRef.current.dated
      : defaultRangeKey
    const cursorRange = cursorRangesRef.current[rangeKey]
    const cursor = cursorRange?.cursors[bucket] ?? null
    if (!cursor || !cursorRange || continuationLoading) return
    setContinuationLoading(true)
    setContinuationError(null)
    try {
      const response = await apiRequest<{ items: Task[]; next_cursor: string | null }>(
        `/api/tasks?status=${filter}&from=${encodeURIComponent(`${cursorRange.from}T00:00:00+07:00`)}&to=${encodeURIComponent(`${cursorRange.to}T00:00:00+07:00`)}&bucket=${bucket}&cursor=${encodeURIComponent(cursor)}&limit=50`,
      )
      setExtraTasks((current) => [...current, ...response.items])
      cursorRange.cursors[bucket] = response.next_cursor
      let nextRangeKey = rangeKey
      if (!response.next_cursor && bucket === 'dated') {
        const pendingRange = Object.entries(cursorRangesRef.current).find(
          ([key, state]) => key !== rangeKey && Boolean(state.cursors[bucket]),
        )
        if (pendingRange) nextRangeKey = pendingRange[0]
      }
      continuationRangeByBucketRef.current[bucket] = nextRangeKey
      setBucketCursors((current) => ({
        ...current,
        [bucket]: cursorRangesRef.current[nextRangeKey]?.cursors[bucket] ?? null,
      }))
    } catch (error) {
      setContinuationError({ bucket, text: errorMessage(error) })
    } finally {
      setContinuationLoading(false)
    }
  }

  function quickAdd(event: FormEvent) {
    event.preventDefault()
    const title = quickTitle.trim()
    if (!title || create.isPending) return
    create.mutate({
      id: uuidv7(),
      title,
      body_md: null,
      priority: null,
      due_at: null,
      is_private: false,
    })
  }

  const visibleForFilter = (group: Task[]) =>
    group.filter((task) => filter === 'all' || task.status === filter)

  function renderGroup(day: string, groupTasks: Task[]) {
    const visible = visibleForFilter(groupTasks)
    const completed = visible.filter((task) => task.status === 'completed')
    const open = visible.filter((task) => task.status === 'open')
    if (filter === 'completed' && completed.length === 0) return null
    if (filter === 'open' && open.length === 0) return (
      <Card key={day} data-testid="task-day-group" data-day={day} className="rounded-lg bg-card p-4 shadow-1">
        <h3 className="text-base font-bold" tabIndex={-1}>{formatTimelineDay(day)}</h3>
      </Card>
    )
    const isOpen = completedOpen.has(day)
    return (
      <Card key={day} data-testid="task-day-group" data-day={day} className="space-y-3 rounded-lg bg-card p-4 shadow-1">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-base font-bold" tabIndex={-1}>{formatTimelineDay(day)}</h3>
          {completed.length > 0 && filter !== 'open' ? (
            <Button
              data-testid="task-day-completed-toggle"
              size="lg"
              variant="ghost"
              aria-expanded={isOpen}
              aria-controls={`task-completed-${day}`}
              onClick={() => setCompletedOpen((current) => {
                const next = new Set(current)
                if (next.has(day)) next.delete(day)
                else next.add(day)
                return next
              })}
            >
              Đã xong ({completed.length}) {isOpen ? <ChevronUp /> : <ChevronDown />}
            </Button>
          ) : null}
        </div>
        <div className="space-y-3">
          {open.map((task) => <TaskCard key={task.id} task={task} migratingPins={migratingPins} />)}
          {isOpen ? <div id={`task-completed-${day}`} className="space-y-3">{completed.map((task) => <TaskCard key={task.id} task={task} migratingPins={migratingPins} />)}</div> : null}
        </div>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {groups.overdue.length > 0 && filter !== 'completed' ? (
        <div ref={overdueRef} data-testid="task-overdue-earlier-group" className="space-y-3">
          <h3 className="text-base font-bold" tabIndex={-1}>Quá hạn trước đó</h3>
          {groups.overdue.map((task) => <TaskCard key={task.id} task={task} migratingPins={migratingPins} />)}
        </div>
      ) : null}
      {groups.overdue.length > 0 && filter !== 'completed' ? (
        <Button data-testid="overdue-banner" size="lg" variant="outline" onClick={() => overdueRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
          Xem việc quá hạn
        </Button>
      ) : null}
      <section aria-labelledby="quick-add-heading">
        <h2 className="sr-only" id="quick-add-heading">Thêm task</h2>
        <form className="flex gap-2" onSubmit={quickAdd}>
          <Input data-testid="quick-add-input" ref={quickInputRef} className="h-11 flex-1 rounded-lg bg-card px-4 shadow-1" aria-label="Thêm task nhanh" placeholder="Thêm việc rồi lưu…" value={quickTitle} onChange={(event) => setQuickTitle(event.target.value)} />
          <Button data-testid="quick-add-submit" className="h-11 rounded-lg px-5" size="lg" type="submit" disabled={!quickTitle.trim() || create.isPending}>{create.isPending ? 'Đang thêm…' : 'Thêm'}</Button>
        </form>
        {create.isError ? <p className="mt-2 text-sm text-bad" role="alert">{errorMessage(create.error)}</p> : null}
        <div className="mt-2 px-1">
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild><Button className="h-auto py-1 pl-0! pr-0! text-xs" size="sm" variant="link"><Plus data-icon="inline-start" />Thêm chi tiết</Button></DialogTrigger>
            <DialogContent data-testid="task-create-dialog" className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
              <DialogHeader><DialogTitle>Tạo task</DialogTitle><DialogDescription>Thêm ghi chú, ưu tiên, hạn hoặc chế độ riêng tư.</DialogDescription></DialogHeader>
              <TaskForm submitLabel="Tạo task" pending={create.isPending} onSubmit={(payload) => create.mutate({ ...payload, id: uuidv7() })} onCancel={() => setCreateOpen(false)} />
            </DialogContent>
          </Dialog>
        </div>
      </section>
      <section aria-labelledby="task-list-heading" className="space-y-3">
        <h2 className="sr-only" id="task-list-heading">Danh sách task</h2>
        <div className="flex flex-wrap gap-1" role="group" aria-label="Lọc task">
          {(['open', 'completed', 'all'] as ListView[]).map((value) => <Button data-testid={`filter-${value}`} className="rounded-full px-4" size="lg" variant={filter === value ? 'secondary' : 'ghost'} aria-pressed={filter === value} key={value} onClick={() => setFilter(value)}>{listFilterLabels[value]}</Button>)}
        </div>
        {timeline.isPending ? <p className="text-sm text-muted-foreground">Đang tải task…</p> : null}
        {timeline.isError ? <div className="flex flex-wrap items-center gap-3"><p className="text-sm text-bad" role="alert">Không tải được việc. Thử lại.</p><Button variant="outline" size="lg" onClick={() => void timeline.refetch()}>Thử lại</Button></div> : null}
        {timeline.data && tasks.length === 0 ? <Card className="rounded-lg border border-dashed bg-transparent p-6 text-center text-sm text-muted-foreground">Không có việc phù hợp trong khung bảy ngày.</Card> : null}
        <div data-testid="task-list" className="space-y-3">
          {groups.dateGroups.map(({ day, tasks: groupTasks }) => renderGroup(day, groupTasks))}
          {groups.undated.some((task) => task.status === 'open') && filter !== 'completed' ? <section data-testid="task-undated-group" className="space-y-3"><h3 className="text-base font-bold">Chưa xếp ngày</h3>{groups.undated.filter((task) => task.status === 'open').map((task) => <TaskCard key={task.id} task={task} migratingPins={migratingPins} />)}</section> : null}
          {groups.undated.some((task) => task.status === 'completed') && filter !== 'open' ? <section data-testid="task-undated-group" className="space-y-3"><h3 className="text-base font-bold">Chưa xếp ngày</h3><Button data-testid="task-day-completed-toggle" size="lg" variant="ghost" aria-expanded={completedOpen.has('undated')} onClick={() => setCompletedOpen((current) => new Set(current).has('undated') ? new Set([...current].filter((key) => key !== 'undated')) : new Set([...current, 'undated']))}>Đã xong ({groups.undated.filter((task) => task.status === 'completed').length})</Button>{completedOpen.has('undated') ? groups.undated.filter((task) => task.status === 'completed').map((task) => <TaskCard key={task.id} task={task} migratingPins={migratingPins} />) : null}</section> : null}
        </div>
        <div className="flex flex-wrap gap-2 pt-2">
          <Button data-testid="task-load-earlier" size="lg" variant="outline" disabled={loadingDirection !== null || !hasPrevious} title={!hasPrevious ? 'Không còn ngày trước trong phạm vi có thể xem' : undefined} onClick={() => void loadBlock('earlier')}>{loadingDirection === 'earlier' ? 'Đang tải…' : 'Xem thêm ngày trước'}</Button>
          <Button data-testid="task-load-later" size="lg" variant="outline" disabled={loadingDirection !== null || !hasNext} title={!hasNext ? 'Không còn ngày sau trong phạm vi có thể xem' : undefined} onClick={() => void loadBlock('later')}>{loadingDirection === 'later' ? 'Đang tải…' : 'Xem thêm ngày sau'}</Button>
          <Button data-testid="task-history" size="lg" variant="ghost" disabled={loadingDirection !== null || !hasPrevious} title={!hasPrevious ? 'Không còn lịch sử trước đó' : undefined} onClick={() => void loadBlock('earlier')}>Xem toàn bộ lịch sử</Button>
          {bucketCursors.dated ? <Button data-testid="task-load-more-in-day" size="lg" variant="ghost" disabled={continuationLoading} onClick={() => void loadMoreBucket('dated')}>{continuationLoading ? 'Đang tải…' : 'Xem thêm việc trong ngày'}</Button> : null}
          {bucketCursors.overdue && filter !== 'completed' ? <Button data-testid="task-load-more-overdue" size="lg" variant="ghost" disabled={continuationLoading} onClick={() => void loadMoreBucket('overdue')}>{continuationLoading ? 'Đang tải…' : 'Xem thêm việc quá hạn'}</Button> : null}
          {bucketCursors.undated ? <Button data-testid="task-load-more-undated" size="lg" variant="ghost" disabled={continuationLoading} onClick={() => void loadMoreBucket('undated')}>{continuationLoading ? 'Đang tải…' : 'Xem thêm việc chưa xếp ngày'}</Button> : null}
        </div>
        {rangeError ? <div className="flex flex-wrap items-center gap-2" role="status"><p className="text-sm text-bad" role="alert">{rangeError.text}</p><Button size="lg" variant="outline" disabled={loadingDirection !== null} onClick={() => void loadBlock(rangeError.direction)}>Thử lại</Button></div> : null}
        {continuationError ? <div className="flex flex-wrap items-center gap-2" role="status"><p className="text-sm text-bad" role="alert">{continuationError.text}</p><Button size="lg" variant="outline" disabled={continuationLoading} onClick={() => void loadMoreBucket(continuationError.bucket)}>Thử lại</Button></div> : null}
        <p className="text-sm text-muted-foreground" aria-live="polite">Đang xem {loadedStart} đến {loadedEnd}.</p>
      </section>
    </div>
  )
}

type CreateSource = 'quick' | 'detail'
type ListView = TaskFilter | 'overdue'

const LEGACY_PIN_IDS_KEY = 'microsched:pinned-task-ids'
const PINNED_MIGRATED_KEY = 'microsched:pinned-migrated-v1'

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

function formatDue(value: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: VIETNAM_TIME_ZONE,
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

const listFilterLabels: Record<ListView, string> = {
  ...filterLabels,
  overdue: 'Trễ hạn',
}

function vietnamDateKey(value: string): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: VIETNAM_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(value))
  const values = Object.fromEntries(parts.filter((part) => part.type !== 'literal').map((part) => [part.type, part.value]))
  return `${values.year}-${values.month}-${values.day}`
}

type TaskTimelineResponse = {
  items: Task[]
  next_cursor: string | null
  bucket_cursors: Record<string, string | null>
  has_previous: boolean
  has_next: boolean
  loaded_range_start: string
  loaded_range_end: string
  counts: Record<string, number>
}

type TimelineBucket = 'overdue' | 'dated' | 'undated'

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

// ⚡ Bolt: Wrapped TaskCard in React.memo to prevent unnecessary re-renders.
// The parent TasksScreen holds state for the quick add input (quickTitle), which updates on every keystroke.
// Memoizing TaskCard ensures that typing in the quick add input does not trigger a re-render
// of all task cards in the list, significantly improving typing responsiveness.
// Impact: Reduces re-renders by ~100% per keystroke for unchanged task cards.
const TaskCard = memo(function TaskCard({
  task,
  migratingPins,
}: {
  task: Task
  migratingPins: boolean
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
  /* 010b §2 mục 9: dời hạn làm đổi chip task trên lịch, nên refresh cả họ
     ["calendar"] bên cạnh ["tasks"] (lịch không mounted thì không tốn mạng). */
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: taskInvalidationKey })
    void queryClient.invalidateQueries({ queryKey: ['calendar'] })
  }
  const reschedule = useMutation({
    mutationFn: (variables: { next: string | null; previous: string | null }) =>
      apiRequest<Task>(`/api/tasks/${task.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ due_at: variables.next }),
      }),
    onSuccess: (_data, variables) => {
      refresh()
      toast(
        <span className="block min-w-0 max-w-full break-words">
          Đã dời “{task.title}”
        </span>,
        {
          duration: 8000,
          action: {
            label: 'Hoàn tác',
            onClick: () =>
              reschedule.mutate({ next: variables.previous, previous: null }),
          },
        },
      )
    },
  })
  const update = useMutation({
    mutationFn: (
      payload: Partial<TaskPayload> & { status?: TaskStatus; pinned?: boolean },
    ) =>
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
      refresh()
      toast(
        <span className="block min-w-0 max-w-full break-words">
          Đã xoá &quot;{task.title}&quot;
        </span>,
        {
          duration: 10000,
          action: {
            label: 'Hoàn tác',
            onClick: () => void restoreTask(task.id, refresh),
          },
        },
      )
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

  /* Dialog chi tiết mở bằng state chứ không bọc `DialogTrigger`, nên Radix không có
     `triggerRef` để trả focus về khi đóng — focus rơi xuống `body` và người dùng bàn
     phím phải Tab lại từ đầu trang. Tự nhớ lấy nút đã mở nó. */
  const detailsReturnRef = useRef<HTMLButtonElement | null>(null)

  function openDetails(event: MouseEvent<HTMLButtonElement>) {
    // Same guard as `openDetailsFromCard`: the title itself is a `<button>`,
    // and today's browsers happen not to let a drag form a selection over
    // one — but that is a browser quirk, not something this code enforces.
    // Checking here too means the guard still holds if that ever changes.
    const selection = window.getSelection()
    if (selection && !selection.isCollapsed) return

    detailsReturnRef.current = event.currentTarget
    setEditing(false)
    setDetailsOpen(true)
  }

  function openDetailsFromCard(event: MouseEvent<HTMLDivElement>) {
    const selection = window.getSelection()
    if (selection && !selection.isCollapsed) return

    const target = event.target
    if (!(target instanceof Element)) return
    if (
      target.closest(
        'button, a, input, textarea, select, label, [role="button"], [contenteditable="true"]',
      )
    ) {
      return
    }

    const title = event.currentTarget.querySelector<HTMLButtonElement>(
      '[data-testid="task-title"]',
    )
    if (!title) return
    detailsReturnRef.current = title
    setEditing(false)
    setDetailsOpen(true)
  }

  function openEditor(event: MouseEvent<HTMLButtonElement>) {
    detailsReturnRef.current = event.currentTarget
    setEditing(true)
    setDetailsOpen(true)
  }

  function rescheduleTo(daysFromNow: number) {
    reschedule.mutate({
      next: endOfDayVietnam(addVietnamDays(todayInVietnam(), daysFromNow)),
      previous: task.due_at,
    })
  }

  return (
    <>
      <Card
        data-testid="task-card"
        data-task-id={task.id}
        onClick={openDetailsFromCard}
        className={[
          'group/task relative gap-3 overflow-visible rounded-lg px-4 py-4 shadow-2 ring-0 transition-shadow',
          task.pinned ? 'bg-brand-50 shadow-rose' : 'bg-card',
          task.status === 'completed' ? 'opacity-70' : '',
        ].join(' ')}
      >
        <div className="flex items-start gap-3">
          <Checkbox
            data-testid="task-checkbox"
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
              {task.pinned ? <Pin className="size-4 text-primary" aria-hidden="true" /> : null}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    data-testid="task-title"
                    className={[
                      // Tràn 733px chữ trong thẻ rộng 318px, đè lên cả ba nút hành động
                      // (QA 2026-07-25). Phải đủ BA thứ, thiếu một là không chữa được:
                      //   `shrink`      — lớp gốc của Button có `shrink-0`, tức flex item
                      //                   từ chối co, nên hộp luôn rộng bằng max-content
                      //                   và chẳng có gì ép chữ phải xuống dòng cả.
                      //   `min-w-0`     — gỡ `min-width:auto` mặc định của flex item.
                      //   `break-words` — `whitespace-normal` chỉ xuống dòng ở khoảng
                      //                   trắng; một cụm 70 ký tự liền thì không có chỗ.
                      'h-auto min-w-0 shrink justify-start whitespace-normal break-words p-0 text-left text-base font-bold tracking-tight hover:bg-transparent',
                      task.status === 'completed' ? 'line-through' : '',
                    ].join(' ')}
                    variant="ghost"
                    aria-label={`Mở chi tiết ${task.title}`}
                    onClick={openDetails}
                  >
                    {task.title}
                  </Button>
                </TooltipTrigger>
                {task.body_md || task.items.length > 0 ? (
                  <TooltipContent>
                    {task.items.length > 0 ? (
                      <div>
                        <span className="block text-xs font-extrabold tracking-wide uppercase opacity-70">
                          Checklist ({task.items.length})
                        </span>
                        <ol className="mt-1 space-y-0.5">
                          {task.items.slice(0, 3).map((item, index) => (
                            <li key={item.id} className="flex gap-1.5">
                              <span className="opacity-60">{index + 1}.</span>
                              {item.content}
                            </li>
                          ))}
                        </ol>
                        {task.items.length > 3 ? (
                          <p className="mt-1 text-xs opacity-70 italic">
                            … và {task.items.length - 3} mục nữa
                          </p>
                        ) : null}
                      </div>
                    ) : null}
                    {task.body_md ? (
                      <div className={task.items.length > 0 ? 'mt-2' : ''}>
                        <span className="block text-xs font-extrabold tracking-wide uppercase opacity-70">
                          Ghi chú
                        </span>
                        {task.body_md}
                      </div>
                    ) : null}
                  </TooltipContent>
                ) : null}
              </Tooltip>
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

            {isOverdue(task) ? (
              <div className="mt-2 flex flex-wrap gap-2">
                <Button
                  data-testid="task-reschedule-today"
                  size="sm"
                  variant="softRose"
                  disabled={reschedule.isPending || update.isPending}
                  onClick={() => rescheduleTo(0)}
                >
                  Hôm nay
                </Button>
                <Button
                  data-testid="task-reschedule-tomorrow"
                  size="sm"
                  variant="softRose"
                  disabled={reschedule.isPending || update.isPending}
                  onClick={() => rescheduleTo(1)}
                >
                  Mai
                </Button>
                <Button
                  data-testid="task-reschedule-day-after"
                  size="sm"
                  variant="softRose"
                  disabled={reschedule.isPending || update.isPending}
                  onClick={() => rescheduleTo(2)}
                >
                  Ngày kia
                </Button>
              </div>
            ) : null}
          </div>

          <div className="flex shrink-0 flex-wrap justify-end gap-2">
            <Button
              data-testid="task-pin"
              size="icon-lg"
              variant="ghost"
              aria-label={task.pinned ? `Bỏ ghim ${task.title}` : `Ghim ${task.title}`}
              disabled={migratingPins || update.isPending}
              onClick={() => update.mutate({ pinned: !task.pinned })}
            >
              {task.pinned ? <PinOff /> : <Pin />}
            </Button>
            <Button
              data-testid="task-edit"
              size="icon-lg"
              variant="ghost"
              aria-label={`Sửa ${task.title}`}
              onClick={openEditor}
            >
              <Edit3 />
            </Button>
            <Button
              data-testid="task-delete"
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
                  data-testid="task-checkbox"
                  aria-label={`Đánh dấu ${item.content} hoàn thành`}
                  checked={item.is_completed}
                  disabled={changeItem.isPending}
                  onCheckedChange={(checked) =>
                    changeItem.mutate({ item, isCompleted: checked === true })
                  }
                />
                <span
                  className={[
                    // Cùng bệnh với tiêu đề: mục checklist dài hoặc một cụm liền
                    // không dấu cách sẽ đẩy rộng cả thẻ nếu không có `min-w-0` để
                    // được phép co, và `break-words` để có chỗ mà cắt.
                    'min-w-0 break-words',
                    item.is_completed ? 'text-muted-foreground line-through' : '',
                  ].join(' ')}
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

      </Card>

      <Dialog
        open={detailsOpen}
        onOpenChange={(open) => {
          setDetailsOpen(open)
          if (!open) setEditing(false)
        }}
      >
        <DialogContent
          data-testid="task-detail-dialog"
          className="max-h-[85vh] overflow-y-auto sm:max-w-lg"
          // `isConnected` chứ không phải chỉ kiểm null: nút mở có thể đã biến mất
          // khỏi cây (thẻ vừa bị xoá, danh sách vừa được lọc lại). Focus vào một
          // node đã tháo là không làm gì cả — thà nhường lại cho xử lý mặc định.
          onCloseAutoFocus={(event) => {
            const opener = detailsReturnRef.current
            if (!opener?.isConnected) return
            event.preventDefault()
            opener.focus()
          }}
        >
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
})

export function LegacyTasksScreen() {
  const queryClient = useQueryClient()
  const quickInputRef = useRef<HTMLInputElement>(null)
  const [filter, setFilter] = useState<ListView>('open')
  const [quickTitle, setQuickTitle] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [migratingPins, setMigratingPins] = useState(false)

  const tasks = useQuery({
    queryKey: taskQueryKey('all'),
    queryFn: () =>
      apiRequest<{ items: Task[] }>('/api/tasks?status=all&limit=100'),
    refetchInterval: taskRefetchInterval,
    retry: (failureCount, error) =>
      !(error instanceof UnauthenticatedError) && failureCount < 2,
  })

  useEffect(() => {
    if (!tasks.isSuccess || !navigator.onLine) return

    let pinnedIds: string[]
    try {
      if (window.localStorage.getItem(PINNED_MIGRATED_KEY) === '1') return
      const stored = JSON.parse(window.localStorage.getItem(LEGACY_PIN_IDS_KEY) ?? '[]')
      pinnedIds = Array.isArray(stored)
        ? [...new Set(stored.filter((value): value is string => typeof value === 'string'))]
        : []
    } catch (error) {
      console.warn('Could not read legacy pinned tasks; migration will retry later.', error)
      return
    }
    if (pinnedIds.length === 0) return

    try {
      // This synchronous marker closes the two-tab race before the first PATCH starts.
      window.localStorage.setItem(PINNED_MIGRATED_KEY, '1')
    } catch (error) {
      console.warn('Could not claim legacy pin migration; migration will retry later.', error)
      return
    }

    queueMicrotask(() => setMigratingPins(true))
    void Promise.allSettled(
      pinnedIds.map((taskId) =>
        apiRequest<Task>(`/api/tasks/${taskId}`, {
          method: 'PATCH',
          body: JSON.stringify({ pinned: true }),
        }),
      ),
    ).then((results) => {
      const retryIds = results.flatMap((result, index) => {
        if (result.status === 'fulfilled') return []
        if (result.reason instanceof ApiError && result.reason.status === 404) return []

        const shouldRetry =
          (result.reason instanceof ApiError && result.reason.status >= 500) ||
          !(
            result.reason instanceof ApiError ||
            result.reason instanceof UnauthenticatedError
          )
        if (shouldRetry) {
          console.warn(
            'Could not migrate a legacy pinned task; migration will retry later.',
            result.reason,
          )
          return [pinnedIds[index]]
        }
        return []
      })

      try {
        if (retryIds.length === 0) {
          window.localStorage.removeItem(LEGACY_PIN_IDS_KEY)
        } else {
          window.localStorage.setItem(LEGACY_PIN_IDS_KEY, JSON.stringify(retryIds))
          // A partial migration is not complete: release the cross-tab claim so a
          // later app open can retry only the network/5xx failures retained above.
          window.localStorage.removeItem(PINNED_MIGRATED_KEY)
        }
      } catch (error) {
        console.warn('Could not persist legacy pin migration progress.', error)
        try {
          window.localStorage.removeItem(PINNED_MIGRATED_KEY)
        } catch {
          // The original per-ID list remains the retry source when storage is blocked.
        }
      }

      void queryClient.invalidateQueries({ queryKey: taskInvalidationKey })
      setMigratingPins(false)
    })
  }, [queryClient, tasks.isSuccess])

  const create = useMutation({
    mutationFn: ({ payload }: { payload: TaskPayload; source: CreateSource }) =>
      apiRequest<Task>('/api/tasks', {
        method: 'POST',
        body: JSON.stringify({ ...payload, items: [] }),
      }),
    // Cùng luật với `refresh()` của TaskCard, và đây mới là chỗ bug được BÁO:
    // nút "Đang thêm…" đọc `create.isPending`, mà React Query giữ `isPending` cho
    // tới khi `onSuccess` resolve. Await ở đây là bắt người dùng nhìn nút đứng im
    // suốt lượt tải lại DÙ task đã lưu xong. Dọn giao diện trước, làm mới sau.
    onSuccess: (_task, variables) => {
      if (variables.source === 'quick') {
        setQuickTitle('')
        window.requestAnimationFrame(() => quickInputRef.current?.focus())
      } else {
        setCreateOpen(false)
      }

      void queryClient.invalidateQueries({ queryKey: taskInvalidationKey })
    },
  })

  const overdueCount = useMemo(
    () => tasks.data?.items.filter(isOverdue).length ?? 0,
    [tasks.data?.items],
  )

  // Completing the final overdue task closes that derived view immediately;
  // keeping this as a derived value avoids a cascading render from an effect.
  const activeFilter: ListView =
    filter === 'overdue' && overdueCount === 0 ? 'open' : filter

  const visibleTasks = useMemo(() => {
    const items = tasks.data?.items ?? []

    return items
      .filter((task) =>
        activeFilter === 'overdue'
          ? isOverdue(task)
          : activeFilter === 'all' || task.status === activeFilter,
      )
  }, [activeFilter, tasks.data?.items])

  function quickAdd(event: FormEvent) {
    event.preventDefault()
    const title = quickTitle.trim()
    if (!title || create.isPending) return

    create.mutate({
      source: 'quick',
      payload: {
        id: uuidv7(),
        title,
        body_md: null,
        priority: null,
        due_at: null,
        is_private: false,
      },
    })
  }

  const filterValues: ListView[] = ['open', 'completed', 'all']
  if (overdueCount > 0 || activeFilter === 'overdue') filterValues.push('overdue')

  return (
    <div className="space-y-4">
      {overdueCount > 0 ? (
        <div
          role="status"
        >
          <Button
            data-testid="overdue-banner"
            className="h-auto min-h-11 w-full justify-start rounded-lg bg-bad-bg px-4 py-3 text-sm font-bold text-bad hover:bg-bad-bg"
            size="lg"
            aria-label={`Xem ${overdueCount} việc trễ hạn`}
            onClick={() => setFilter('overdue')}
          >
            <AlertTriangle className="size-5 shrink-0" aria-hidden="true" />
            {/* Tiếng Việt không đổi dạng số nhiều — đừng thêm nhánh đếm ở đây. */}
            <span>{overdueCount} việc trễ hạn</span>
          </Button>
        </div>
      ) : null}

      <section aria-labelledby="quick-add-heading">
        <h2 className="sr-only" id="quick-add-heading">
          Thêm task
        </h2>
        <form className="flex gap-2" onSubmit={quickAdd}>
          <Input
            data-testid="quick-add-input"
            ref={quickInputRef}
            className="h-11 flex-1 rounded-lg bg-card px-4 shadow-1"
            aria-label="Thêm task nhanh"
            placeholder="Thêm việc rồi lưu…"
            value={quickTitle}
            onChange={(event) => setQuickTitle(event.target.value)}
          />
          <Button
            data-testid="quick-add-submit"
            className="h-11 rounded-lg px-5"
            size="lg"
            type="submit"
            disabled={!quickTitle.trim() || create.isPending}
          >
            {create.isPending ? 'Đang thêm…' : 'Thêm'}
          </Button>
        </form>

        {/* Lỗi của `create` trước đây CHỈ được vẽ bên trong Dialog, mà Dialog đóng
            thì `DialogContent` không còn trong cây. Nghĩa là thêm nhanh mà hỏng thì
            nút lặng lẽ quay từ "Đang thêm…" về "Thêm" và không nói gì cả — đúng cái
            "không có cách nào để THẤT BẠI" mà 008i sinh ra để chữa. Lọc theo
            `source` để một lần hỏng không hiện lời báo ở cả hai nơi. */}
        {create.isError && create.variables?.source === 'quick' ? (
          <p data-testid="quick-add-error" className="mt-2 px-1 text-sm text-bad" role="alert">
            {errorMessage(create.error)}
          </p>
        ) : null}

        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 px-1">
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button className="h-auto py-1 pl-0! pr-0! text-xs" size="sm" variant="link">
                <Plus data-icon="inline-start" />
                Thêm chi tiết
              </Button>
            </DialogTrigger>
            <DialogContent
              data-testid="task-create-dialog"
              className="max-h-[85vh] overflow-y-auto sm:max-w-lg"
            >
              <DialogHeader>
                <DialogTitle>Tạo task</DialogTitle>
                <DialogDescription>
                  Thêm ghi chú, ưu tiên, hạn hoặc chế độ riêng tư.
                </DialogDescription>
              </DialogHeader>
              <TaskForm
                submitLabel="Tạo task"
                pending={create.isPending}
                onSubmit={(payload) =>
                  create.mutate({ payload: { ...payload, id: uuidv7() }, source: 'detail' })
                }
                onCancel={() => setCreateOpen(false)}
              />
              {create.isError && create.variables?.source === 'detail' ? (
                <p className="text-sm text-bad" role="alert">
                  {errorMessage(create.error)}
                </p>
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
            {filterValues.map((value) => (
              <Button
                data-testid={`filter-${value}`}
                className="rounded-full px-4"
                size="lg"
                variant={activeFilter === value ? 'selected' : 'ghost'}
                aria-pressed={activeFilter === value}
                key={value}
                onClick={() => setFilter(value)}
              >
                {listFilterLabels[value]}
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

        <div data-testid="task-list" className="space-y-3">
          {visibleTasks.map((task) => (
            <TaskCard
              task={task}
              migratingPins={migratingPins}
              key={task.id}
            />
          ))}
        </div>
      </section>
    </div>
  )
}
