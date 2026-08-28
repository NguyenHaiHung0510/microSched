import { type FormEvent, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Edit3, Plus, Trash2 } from 'lucide-react'

import { apiRequest } from '@/api'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import {
  canSubmitTask,
  type TaskDuePrecision,
  type TaskFormState,
  type TaskWritePayload,
  type TaskPriority,
  taskInvalidationKey,
  taskPayload,
  transitionTaskDuePrecision,
} from '@/task-ui'
import { todayInVietnam, toVietnamDateTimeInput } from '@/calendar-ui'
import { errorMessage } from '@/task-undo'

export type TaskItem = {
  id: string
  content: string
  is_completed: boolean
  position: number
}

type InitialTask = {
  id?: string
  title: string
  body_md: string | null
  priority: TaskPriority | null
  due_precision: TaskDuePrecision
  due_on: string | null
  due_at: string | null
  is_private: boolean
  items?: TaskItem[]
}

const priorityLabels: Record<TaskPriority, string> = {
  p1: 'P1',
  p2: 'P2',
  p3: 'P3',
}

const duePrecisionLabels: Record<TaskDuePrecision, string> = {
  date: 'Ngày',
  datetime: 'Ngày + giờ',
  none: 'Chưa xếp lịch',
}

function initialDue(initial?: InitialTask): { precision: TaskDuePrecision; day: string; time: string } {
  if (!initial) return { precision: 'date', day: todayInVietnam(), time: '' }
  if (initial.due_precision === 'date') {
    return { precision: 'date', day: initial.due_on ?? '', time: '' }
  }
  if (initial.due_precision === 'datetime') {
    const local = toVietnamDateTimeInput(initial.due_at)
    const [day = '', time = ''] = local.split('T')
    return { precision: 'datetime', day, time }
  }
  return { precision: 'none', day: '', time: '' }
}

function selectedPriorityLabel(priority: TaskPriority | ''): string {
  return priority ? priorityLabels[priority] : 'Không đặt'
}

function PersistedChecklistSection({
  taskId,
  initialItems,
  disabled,
  onPendingChange,
}: {
  taskId: string
  initialItems: TaskItem[]
  disabled: boolean
  onPendingChange: (pending: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [items, setItems] = useState<TaskItem[]>(initialItems)
  const [newContent, setNewContent] = useState('')
  const [editingItemId, setEditingItemId] = useState<string | null>(null)
  const [editingContent, setEditingContent] = useState('')

  const refreshQueries = () => {
    void queryClient.invalidateQueries({ queryKey: taskInvalidationKey })
    void queryClient.invalidateQueries({ queryKey: ['calendar'] })
  }

  const addItemMutation = useMutation({
    mutationFn: (content: string) =>
      apiRequest<TaskItem>(`/api/tasks/${taskId}/items`, {
        method: 'POST',
        body: JSON.stringify({ content, position: items.length }),
      }),
    onMutate: () => onPendingChange(true),
    onSettled: () => onPendingChange(false),
    onSuccess: (createdItem) => {
      setNewContent('')
      setItems((prev) => [...prev, createdItem])
      refreshQueries()
    },
  })

  const updateContentMutation = useMutation({
    mutationFn: ({ itemId, content }: { itemId: string; content: string }) =>
      apiRequest<TaskItem>(`/api/tasks/${taskId}/items/${itemId}`, {
        method: 'PATCH',
        body: JSON.stringify({ content }),
      }),
    onMutate: () => onPendingChange(true),
    onSettled: () => onPendingChange(false),
    onSuccess: (updatedItem) => {
      setItems((prev) =>
        prev.map((i) => (i.id === updatedItem.id ? updatedItem : i)),
      )
      setEditingItemId(null)
      setEditingContent('')
      refreshQueries()
    },
  })

  const toggleCompletedMutation = useMutation({
    mutationFn: ({ item, isCompleted }: { item: TaskItem; isCompleted: boolean }) =>
      apiRequest<TaskItem>(`/api/tasks/${taskId}/items/${item.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_completed: isCompleted }),
      }),
    onMutate: () => onPendingChange(true),
    onSettled: () => onPendingChange(false),
    onSuccess: (updatedItem) => {
      setItems((prev) =>
        prev.map((i) => (i.id === updatedItem.id ? updatedItem : i)),
      )
      refreshQueries()
    },
  })

  const removeItemMutation = useMutation({
    mutationFn: (item: TaskItem) =>
      apiRequest<void>(`/api/tasks/${taskId}/items/${item.id}`, {
        method: 'DELETE',
      }),
    onMutate: () => onPendingChange(true),
    onSettled: () => onPendingChange(false),
    onSuccess: (_data, item) => {
      setItems((prev) => prev.filter((i) => i.id !== item.id))
      if (editingItemId === item.id) {
        setEditingItemId(null)
        setEditingContent('')
      }
      refreshQueries()
    },
  })

  const childPending =
    addItemMutation.isPending ||
    updateContentMutation.isPending ||
    toggleCompletedMutation.isPending ||
    removeItemMutation.isPending

  const childError =
    addItemMutation.error ??
    updateContentMutation.error ??
    toggleCompletedMutation.error ??
    removeItemMutation.error

  function addPersisted() {
    const trimmed = newContent.trim()
    if (!trimmed || childPending || disabled) return
    addItemMutation.mutate(trimmed)
  }

  function startEdit(item: TaskItem) {
    setEditingItemId(item.id)
    setEditingContent(item.content)
  }

  function saveEdit(item: TaskItem) {
    const trimmed = editingContent.trim()
    if (!trimmed || childPending || disabled) return
    updateContentMutation.mutate({ itemId: item.id, content: trimmed })
  }

  function cancelEdit() {
    setEditingItemId(null)
    setEditingContent('')
  }

  return (
    <div className="space-y-3 rounded-lg border border-input p-3" data-testid="task-checklist-section">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">Checklist (mục nhỏ)</span>
        {items.length > 0 ? (
          <span className="text-xs text-muted-foreground">
            {items.filter((i) => i.is_completed).length}/{items.length} mục
          </span>
        ) : null}
      </div>

      <div className="space-y-2">
        {items.map((item) =>
          editingItemId === item.id ? (
            <div
              key={item.id}
              data-testid="task-item"
              data-task-item-id={item.id}
              className="flex min-h-9 items-center gap-2 rounded-md bg-muted/40 px-2 py-1 text-sm"
            >
              <Input
                data-testid="task-item-edit-input"
                className="h-8 flex-1 bg-card md:text-sm"
                value={editingContent}
                disabled={disabled || childPending}
                autoFocus
                onChange={(e) => setEditingContent(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    saveEdit(item)
                  } else if (e.key === 'Escape') {
                    e.preventDefault()
                    cancelEdit()
                  }
                }}
              />
              <Button
                data-testid="task-item-edit-save"
                size="xs"
                type="button"
                variant="secondary"
                disabled={!editingContent.trim() || disabled || childPending}
                onClick={() => saveEdit(item)}
              >
                {updateContentMutation.isPending ? 'Đang lưu…' : 'Lưu'}
              </Button>
              <Button
                data-testid="task-item-edit-cancel"
                size="xs"
                type="button"
                variant="outline"
                disabled={disabled || childPending}
                onClick={cancelEdit}
              >
                Huỷ
              </Button>
            </div>
          ) : (
            <div
              key={item.id}
              data-testid="task-item"
              data-task-item-id={item.id}
              className="flex min-h-9 items-center justify-between gap-2 rounded-md bg-muted/40 px-2 py-1 text-sm"
            >
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <Checkbox
                  data-testid="task-item-checkbox"
                  aria-label={`Đánh dấu ${item.content} hoàn thành`}
                  checked={item.is_completed}
                  disabled={disabled || childPending}
                  onCheckedChange={(checked) =>
                    toggleCompletedMutation.mutate({ item, isCompleted: checked === true })
                  }
                />
                <span
                  data-testid="task-item-content"
                  className={`min-w-0 flex-1 break-words ${
                    item.is_completed ? 'text-muted-foreground line-through' : ''
                  }`}
                >
                  {item.content}
                </span>
              </div>
             <div className="flex shrink-0 items-center gap-1">
               <Button
                 data-testid="task-item-edit"
                 size="icon-sm"
                 variant="ghost"
                 type="button"
                  className="size-11 min-h-11 min-w-11 sm:size-8 sm:min-h-8 sm:min-w-8"
                  aria-label={`Sửa mục ${item.content}`}
                  disabled={disabled || childPending}
                  onClick={() => startEdit(item)}
                >
                  <Edit3 className="size-4" />
                </Button>
                <Button
                  data-testid="task-item-delete"
                  size="icon-sm"
                  variant="ghost"
                  type="button"
                  className="size-11 min-h-11 min-w-11 sm:size-8 sm:min-h-8 sm:min-w-8 text-bad hover:text-bad"
                  aria-label={`Xoá mục ${item.content}`}
                  disabled={disabled || childPending}
                  onClick={() => removeItemMutation.mutate(item)}
                >
                  <Trash2 className="size-4" />
                </Button>
              </div>
            </div>
          ),
        )}

        <div className="flex gap-2 pt-1">
          <Input
            data-testid="task-item-add-input"
            className="h-10 bg-card"
            placeholder="Thêm checklist…"
            value={newContent}
            disabled={disabled || childPending}
            onChange={(e) => setNewContent(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                addPersisted()
              }
            }}
          />
          <Button
            data-testid="task-item-add-submit"
            size="lg"
            type="button"
            variant="secondary"
            disabled={!newContent.trim() || disabled || childPending}
            onClick={addPersisted}
          >
            <Plus data-icon="inline-start" />
            {addItemMutation.isPending ? 'Đang thêm…' : 'Thêm'}
          </Button>
        </div>
        {childError ? (
          <p className="text-sm text-bad" role="alert">
            {errorMessage(childError)}
          </p>
        ) : null}
      </div>
    </div>
  )
}

export function TaskForm({
  initial,
  submitLabel,
  pending,
  onSubmit,
  onCancel,
}: {
  initial?: InitialTask
  submitLabel: string
  pending: boolean
  onSubmit: (payload: TaskWritePayload) => void
  onCancel?: () => void
}) {
  const taskId = initial?.id

  const [title, setTitle] = useState(initial?.title ?? '')
  const [body, setBody] = useState(initial?.body_md ?? '')
  const [priority, setPriority] = useState<TaskPriority | ''>(initial?.priority ?? '')
  const dueInitial = initialDue(initial)
  const [duePrecision, setDuePrecision] = useState<TaskDuePrecision>(dueInitial.precision)
  const [dueOn, setDueOn] = useState(dueInitial.day)
  const [dueTime, setDueTime] = useState(dueInitial.time)
  const [isPrivate, setIsPrivate] = useState(initial?.is_private ?? false)

  // Checklist state for Create mode (draft items before parent exists)
  const [draftItems, setDraftItems] = useState<string[]>([])
  const [newDraftContent, setNewDraftContent] = useState('')
  const [editingDraftIdx, setEditingDraftIdx] = useState<number | null>(null)
  const [editingDraftContent, setEditingDraftContent] = useState('')
  const [childPending, setChildPending] = useState(false)

  function addDraftItem() {
    const trimmed = newDraftContent.trim()
    if (!trimmed) return
    setDraftItems((prev) => [...prev, trimmed])
    setNewDraftContent('')
  }

  function startEditDraftItem(index: number) {
    setEditingDraftIdx(index)
    setEditingDraftContent(draftItems[index] ?? '')
  }

  function saveEditDraftItem() {
    if (editingDraftIdx === null) return
    const trimmed = editingDraftContent.trim()
    if (!trimmed) return
    setDraftItems((prev) => prev.map((item, i) => (i === editingDraftIdx ? trimmed : item)))
    setEditingDraftIdx(null)
    setEditingDraftContent('')
  }

  function cancelEditDraftItem() {
    setEditingDraftIdx(null)
    setEditingDraftContent('')
  }

  function removeDraftItem(index: number) {
    setDraftItems((prev) => prev.filter((_, i) => i !== index))
    if (editingDraftIdx === index) {
      setEditingDraftIdx(null)
      setEditingDraftContent('')
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (pending || childPending) return
    const state: TaskFormState = {
      title,
      body,
      priority,
      duePrecision,
      dueOn,
      dueTime,
      isPrivate,
    }
    const payload = taskPayload(state)
    if (!taskId) {
      const validDraftItems = draftItems.map((item) => item.trim()).filter(Boolean)
      onSubmit({ ...payload, items: validDraftItems })
    } else {
      onSubmit(payload)
    }
  }

  function changeDuePrecision(value: string) {
    const next = value as TaskDuePrecision
    const schedule = transitionTaskDuePrecision(
      { duePrecision, dueOn, dueTime },
      next,
      todayInVietnam(),
    )
    setDuePrecision(schedule.duePrecision)
    setDueOn(schedule.dueOn)
    setDueTime(schedule.dueTime)
  }

  return (
    <form className="space-y-4" onSubmit={submit}>
      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Tiêu đề</span>
        <Input
          className="h-11 bg-card"
          value={title}
          minLength={1}
          required
          disabled={pending || childPending}
          onChange={(event) => setTitle(event.target.value)}
        />
      </label>

      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Nội dung</span>
        <Textarea
          className="min-h-24 bg-card font-normal"
          value={body}
          disabled={pending || childPending}
          onChange={(event) => setBody(event.target.value)}
        />
      </label>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <span className="text-sm font-semibold">Ưu tiên</span>
          <Select
            value={priority || 'none'}
            disabled={pending || childPending}
            onValueChange={(value) =>
              setPriority(value === 'none' ? '' : (value as TaskPriority))
            }
          >
            <SelectTrigger size="lg" className="w-full bg-card" aria-label="Ưu tiên">
              <span data-selected-priority={priority || 'none'}>
                {selectedPriorityLabel(priority)}
              </span>
            </SelectTrigger>
            <SelectContent position="popper" align="start">
              <SelectItem value="none">Không đặt</SelectItem>
              <SelectItem value="p1">{priorityLabels.p1}</SelectItem>
              <SelectItem value="p2">{priorityLabels.p2}</SelectItem>
              <SelectItem value="p3">{priorityLabels.p3}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <span className="text-sm font-semibold">Lịch</span>
          <Select value={duePrecision} disabled={pending || childPending} onValueChange={changeDuePrecision}>
            <SelectTrigger size="lg" className="w-full bg-card" aria-label="Kiểu lịch">
              <span data-selected-due-precision={duePrecision}>
                {duePrecisionLabels[duePrecision]}
              </span>
            </SelectTrigger>
            <SelectContent position="popper" align="start">
              <SelectItem value="date">Ngày</SelectItem>
              <SelectItem value="datetime">Ngày + giờ</SelectItem>
              <SelectItem value="none">Chưa xếp lịch</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {duePrecision !== 'none' ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block space-y-1.5 text-sm font-semibold">
            <span>Ngày</span>
            <Input className="h-11 bg-card" type="date" value={dueOn} disabled={pending || childPending} onChange={(event) => setDueOn(event.target.value)} />
          </label>
          {duePrecision === 'datetime' ? (
            <label className="block space-y-1.5 text-sm font-semibold">
              <span>Giờ</span>
              <Input className="h-11 bg-card" type="time" value={dueTime} disabled={pending || childPending} onChange={(event) => setDueTime(event.target.value)} />
            </label>
          ) : null}
        </div>
      ) : null}
      {duePrecision === 'datetime' && !dueTime ? (
        <p className="text-sm text-muted-foreground" role="status">Chọn giờ để lưu task có giờ.</p>
      ) : null}

      {/* Checklist section */}
      {!taskId ? (
        <div className="space-y-3 rounded-lg border border-input p-3" data-testid="task-checklist-section">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold">Checklist (mục nhỏ)</span>
            {draftItems.length > 0 ? (
              <span className="text-xs text-muted-foreground">{draftItems.length} mục</span>
            ) : null}
          </div>

          <div className="space-y-2">
            {draftItems.map((item, idx) =>
              editingDraftIdx === idx ? (
                <div
                  key={idx}
                  data-testid="task-item"
                  className="flex min-h-9 items-center gap-2 rounded-md bg-muted/40 px-2 py-1 text-sm"
                >
                  <Input
                    data-testid="task-item-edit-input"
                    className="h-8 flex-1 bg-card md:text-sm"
                    value={editingDraftContent}
                    disabled={pending}
                    autoFocus
                    onChange={(e) => setEditingDraftContent(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        saveEditDraftItem()
                      } else if (e.key === 'Escape') {
                        e.preventDefault()
                        cancelEditDraftItem()
                      }
                    }}
                  />
                  <Button
                    data-testid="task-item-edit-save"
                    size="xs"
                    type="button"
                    variant="secondary"
                    disabled={!editingDraftContent.trim() || pending}
                    onClick={saveEditDraftItem}
                  >
                    Lưu
                  </Button>
                  <Button
                    data-testid="task-item-edit-cancel"
                    size="xs"
                    type="button"
                    variant="outline"
                    disabled={pending}
                    onClick={cancelEditDraftItem}
                  >
                    Huỷ
                  </Button>
                </div>
              ) : (
                <div
                  key={idx}
                  data-testid="task-item"
                  className="flex min-h-9 items-center justify-between gap-2 rounded-md bg-muted/40 px-3 py-1 text-sm"
                >
                  <span data-testid="task-item-content" className="min-w-0 flex-1 break-words">
                    {item}
                  </span>
                 <div className="flex shrink-0 items-center gap-1">
                   <Button
                     data-testid="task-item-edit"
                     size="icon-sm"
                     variant="ghost"
                     type="button"
                      className="size-11 min-h-11 min-w-11 sm:size-8 sm:min-h-8 sm:min-w-8"
                      aria-label={`Sửa mục ${item}`}
                      disabled={pending}
                      onClick={() => startEditDraftItem(idx)}
                    >
                      <Edit3 className="size-4" />
                    </Button>
                    <Button
                      data-testid="task-item-delete"
                      size="icon-sm"
                      variant="ghost"
                      type="button"
                      className="size-11 min-h-11 min-w-11 sm:size-8 sm:min-h-8 sm:min-w-8 text-bad hover:text-bad"
                      aria-label={`Xoá mục ${item}`}
                      disabled={pending}
                      onClick={() => removeDraftItem(idx)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                </div>
              ),
            )}

            <div className="flex gap-2 pt-1">
              <Input
                data-testid="task-item-add-input"
                className="h-10 bg-card"
                placeholder="Thêm checklist…"
                value={newDraftContent}
                disabled={pending}
                onChange={(e) => setNewDraftContent(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addDraftItem()
                  }
                }}
              />
              <Button
                data-testid="task-item-add-submit"
                size="lg"
                type="button"
                variant="secondary"
                disabled={!newDraftContent.trim() || pending}
                onClick={addDraftItem}
              >
                <Plus data-icon="inline-start" />
                Thêm
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <PersistedChecklistSection
          taskId={taskId}
          initialItems={initial?.items ?? []}
          disabled={pending}
          onPendingChange={setChildPending}
        />
      )}

      <label className="flex min-h-11 items-center gap-3 text-sm font-semibold">
        <Checkbox
          className="size-5 rounded-md"
          checked={isPrivate}
          disabled={pending || childPending}
          onCheckedChange={(checked) => setIsPrivate(checked === true)}
        />
        <span>Riêng tư</span>
      </label>

     <div className="flex flex-wrap gap-2 pt-1">
       <Button
         size="lg"
         type="submit"
         disabled={pending || childPending || !canSubmitTask(title, pending, { duePrecision, dueOn, dueTime })}
       >
         {pending ? 'Đang lưu…' : submitLabel}
       </Button>
        {onCancel ? (
          <Button size="lg" variant="outline" type="button" disabled={pending || childPending} onClick={onCancel}>
            Huỷ
          </Button>
        ) : null}
      </div>
    </form>
  )
}
