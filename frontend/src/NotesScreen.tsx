import {
  type FormEvent,
  type MouseEvent,
  memo,
  useMemo,
  useRef,
  useState,
} from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  ChevronUp,
  Clock,
  Edit3,
  LockKeyhole,
  Pencil,
  Pin,
  Plus,
  Sparkles,
  Trash2,
} from 'lucide-react'
import { toast } from 'sonner'

import { apiRequest, UnauthenticatedError } from '@/api'
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { uuidv7 } from '@/lib/uuidv7'
import { NoteForm } from '@/NoteForm'
import { standardRefetchInterval } from '@/query-polling'
import {
  appendFutureReflection,
  deleteFutureReflection,
  fetchAllNotes,
  formatNoteTime,
  NotePageLimitError,
  parseNoteBody,
  sortNotes,
  updateFutureReflection,
  type Note,
  type NoteItem,
  type NotePayload,
  type NoteSortMode,
  type NoteWritePayload,
  noteInvalidationKey,
  noteQueryKey,
} from '@/note-ui'
import { errorMessage, restoreNote } from '@/note-undo'

type CreateSource = 'quick' | 'detail'

function noteLabel(note: Note): string {
  return note.title || 'Không tiêu đề'
}

const NoteCard = memo(function NoteCard({ note }: { note: Note }) {
  const queryClient = useQueryClient()
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [newItem, setNewItem] = useState('')
  const [reflectionOpen, setReflectionOpen] = useState(false)
  const [reflectionText, setReflectionText] = useState('')
  const [editingItemId, setEditingItemId] = useState<string | null>(null)
  const [editingItemContent, setEditingItemContent] = useState('')
  const [editingReflectionIdx, setEditingReflectionIdx] = useState<number | null>(null)
  const [editingReflectionText, setEditingReflectionText] = useState('')
  const parsedBody = useMemo(() => parseNoteBody(note.body_md), [note.body_md])
  const detailsReturnRef = useRef<HTMLButtonElement | null>(null)
  const label = noteLabel(note)

  const refresh = () => void queryClient.invalidateQueries({ queryKey: noteInvalidationKey })
  const update = useMutation({
    mutationFn: (payload: Partial<NoteWritePayload>) =>
      apiRequest<Note>(`/api/notes/${note.id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      setEditing(false)
      refresh()
    },
  })
  const remove = useMutation({
    mutationFn: () => apiRequest<void>(`/api/notes/${note.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      setDetailsOpen(false)
      refresh()
      toast(
        <span className="block min-w-0 max-w-full break-words">
          Đã xoá &quot;{label}&quot;
        </span>,
        {
          duration: 10000,
          action: {
            label: 'Hoàn tác',
            onClick: () => void restoreNote(note.id, refresh),
          },
        },
      )
    },
  })
  const addItem = useMutation({
    mutationFn: (content: string) =>
      apiRequest<NoteItem>(`/api/notes/${note.id}/items`, {
        method: 'POST',
        body: JSON.stringify({ content, position: note.items.length }),
      }),
    onSuccess: () => {
      setNewItem('')
      refresh()
    },
  })
  const changeItem = useMutation({
    mutationFn: ({ item, changes }: { item: NoteItem; changes: Partial<NoteItem> }) =>
      apiRequest<NoteItem>(`/api/notes/${note.id}/items/${item.id}`, {
        method: 'PATCH',
        body: JSON.stringify(changes),
      }),
    onSuccess: () => {
      setEditingItemId(null)
      setEditingItemContent('')
      refresh()
    },
  })
  const reorderItems = useMutation({
    mutationFn: async ({ item, other }: { item: NoteItem; other: NoteItem }) => {
      await Promise.all([
        apiRequest<NoteItem>(`/api/notes/${note.id}/items/${item.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ position: other.position }),
        }),
        apiRequest<NoteItem>(`/api/notes/${note.id}/items/${other.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ position: item.position }),
        }),
      ])
    },
    onSuccess: refresh,
  })
  const removeItem = useMutation({
    mutationFn: (item: NoteItem) =>
      apiRequest<void>(`/api/notes/${note.id}/items/${item.id}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })

  const completedItems = note.items.filter((item) => item.is_completed).length
  const visibleItems = expanded ? note.items : note.items.slice(0, 3)
  const hiddenItems = Math.max(0, note.items.length - 3)
  const mutationError =
    update.error ??
    remove.error ??
    addItem.error ??
    changeItem.error ??
    reorderItems.error ??
    removeItem.error

  function openDetails(event: MouseEvent<HTMLButtonElement>) {
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
      '[data-testid="note-title"]',
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

  function startEditingItem(item: NoteItem) {
    setEditingItemId(item.id)
    setEditingItemContent(item.content)
  }

  function moveItem(index: number, direction: -1 | 1) {
    const other = note.items[index + direction]
    if (other) reorderItems.mutate({ item: note.items[index], other })
  }

  return (
    <>
      <Card
        data-testid="note-card"
        data-note-id={note.id}
        onClick={openDetailsFromCard}
        className="gap-3 overflow-visible rounded-lg bg-card px-4 py-4 shadow-2 ring-0 transition-shadow"
      >
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
          <div className="min-w-0 flex-1 space-y-2 w-full">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2 min-w-0 flex-1">
              {note.pinned ? (
                <Badge data-testid="note-pinned-badge-card" variant="default" className="gap-1 px-1.5 py-0 text-xs">
                  <Pin className="size-3 fill-current" />
                  Đã ghim
                </Badge>
              ) : null}
              <Button
                data-testid="note-title"
                className="h-auto min-w-0 shrink justify-start whitespace-normal break-words p-0 text-left text-base font-bold tracking-tight hover:bg-transparent"
                variant="ghost"
                aria-label={`Mở chi tiết ${label}`}
                onClick={openDetails}
              >
                {label}
              </Button>
              {note.is_private ? (
                <Badge data-testid="note-private-badge-card" variant="secondary">
                  <LockKeyhole data-icon="inline-start" />
                  Riêng tư
                </Badge>
              ) : null}
              </div>
            </div>

            {parsedBody.baseText ? (
              <p className="whitespace-pre-wrap break-words text-sm text-muted-foreground w-full">
                {parsedBody.baseText}
              </p>
            ) : null}

            {parsedBody.reflections.length > 0 ? (
              <div className="space-y-2 pt-1 w-full">
                {parsedBody.reflections.map((refl, idx) => (
                 <div
                   key={refl.id}
                   data-testid="note-reflection-box"
                   className="rounded-md border border-warn/30 bg-warn-bg p-2.5 text-xs text-foreground space-y-1 shadow-sm w-full"
                 >
                    <div className="flex flex-wrap items-center justify-between gap-1 text-xs font-bold text-foreground">
                      <span className="flex flex-wrap items-center gap-1 min-w-0">
                        <span>💬 Lời nhắn từ tương lai</span>
                        <span className="font-semibold text-muted-foreground">({refl.time})</span>
                      </span>
                      <div className="flex items-center gap-0.5 shrink-0">
                        <Button
                          size="icon-xs"
                          variant="ghost"
                          className="size-8 min-h-8 min-w-8 p-0 hover:bg-warn/20"
                          aria-label="Sửa lời nhắn"
                          onClick={(e) => {
                            e.stopPropagation()
                            setEditingReflectionIdx(idx)
                            setEditingReflectionText(refl.text)
                          }}
                        >
                          <Pencil className="size-3" />
                        </Button>
                        <Button
                          size="icon-xs"
                          variant="ghost"
                          className="size-8 min-h-8 min-w-8 p-0 text-bad hover:bg-warn/20 hover:text-bad"
                          aria-label="Xoá lời nhắn"
                          onClick={(e) => {
                            e.stopPropagation()
                            const newBody = deleteFutureReflection(note.body_md, idx)
                            update.mutate({ body_md: newBody })
                          }}
                        >
                          <Trash2 className="size-3" />
                        </Button>
                      </div>
                    </div>
                    <p className="whitespace-pre-wrap break-words text-xs text-foreground">
                      {refl.text}
                    </p>
                  </div>
                ))}
              </div>
            ) : null}

            <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Clock className="size-3 shrink-0" />
                <span>{formatNoteTime(note.created_at)}</span>
                {note.items.length > 0 ? (
                  <span>· {completedItems}/{note.items.length} mục</span>
                ) : null}
              </div>
              <Button
                data-testid="note-future-reflection-trigger"
                size="xs"
                variant="outline"
                className="gap-1 text-xs min-h-8"
                onClick={(e) => {
                  e.stopPropagation()
                  setReflectionOpen(true)
                }}
              >
                <Sparkles className="size-3 text-primary" />
                💬 Gửi lời nhắn tương lai
              </Button>
            </div>
          </div>

          <div className="flex shrink-0 items-center justify-end gap-1 sm:gap-2">
            <Button
              data-testid="note-pin"
              size="icon-lg"
              variant="ghost"
              className={cn('size-11 min-h-11 min-w-11', note.pinned ? 'text-primary' : 'text-muted-foreground')}
              aria-label={note.pinned ? `Bỏ ghim ${label}` : `Ghim ${label}`}
              disabled={update.isPending}
              onClick={(e) => {
                e.stopPropagation()
                update.mutate({ pinned: !note.pinned })
              }}
            >
              <Pin className={cn('size-4', note.pinned && 'fill-primary')} />
            </Button>
            <Button
              data-testid="note-edit"
              size="icon-lg"
              variant="ghost"
              className="size-11 min-h-11 min-w-11"
              aria-label={`Sửa ${label}`}
              onClick={openEditor}
            >
              <Edit3 />
            </Button>
            <Button
              data-testid="note-delete"
              size="icon-lg"
              variant="ghost"
              className="size-11 min-h-11 min-w-11 text-bad hover:text-bad"
              aria-label={`Xoá ${label}`}
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
            >
              <Trash2 />
            </Button>
          </div>
        </div>

        {note.items.length > 0 ? (
          <div className="space-y-2">
            {visibleItems.map((item) => (
              <label
                className="flex min-h-8 items-center gap-3 text-sm"
                data-testid="note-item"
                data-note-item-id={item.id}
                key={item.id}
              >
                <Checkbox
                  data-testid="note-item-checkbox"
                  aria-label={`Đánh dấu ${item.content} hoàn thành`}
                  checked={item.is_completed}
                  disabled={changeItem.isPending}
                  onCheckedChange={(checked) =>
                    changeItem.mutate({ item, changes: { is_completed: checked === true } })
                  }
                />
                <span
                  data-testid="note-item-content"
                  className={`min-w-0 break-words ${
                    item.is_completed ? 'text-muted-foreground line-through' : ''
                  }`}
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

        {mutationError ? <p className="text-sm text-bad">{errorMessage(mutationError)}</p> : null}
      </Card>

      <Dialog
        open={detailsOpen}
        onOpenChange={(open) => {
          setDetailsOpen(open)
          if (!open) {
            setEditing(false)
            setEditingItemId(null)
          }
        }}
      >
        <DialogContent
          data-testid="note-detail-dialog"
          className="max-h-[85vh] overflow-y-auto sm:max-w-lg"
          onCloseAutoFocus={(event) => {
            const opener = detailsReturnRef.current
            if (!opener?.isConnected) return
            event.preventDefault()
            opener.focus()
          }}
        >
          <DialogHeader>
            <DialogTitle>{editing ? `Sửa · ${label}` : label}</DialogTitle>
            <DialogDescription>
              {editing ? 'Cập nhật nội dung hoặc chế độ riêng tư.' : 'Chi tiết ghi chú và checklist.'}
            </DialogDescription>
          </DialogHeader>

          {editing ? (
            <NoteForm
              initial={note}
              submitLabel="Lưu thay đổi"
              pending={update.isPending}
              onSubmit={(payload) => update.mutate(payload)}
              onCancel={() => setEditing(false)}
            />
          ) : (
            <div className="space-y-5">
              {note.is_private ? (
                <Badge data-testid="note-private-badge-detail" variant="secondary">
                  <LockKeyhole data-icon="inline-start" />
                  Riêng tư
                </Badge>
              ) : null}
              {note.pinned ? (
                <Badge data-testid="note-pinned-badge-detail" variant="default" className="gap-1">
                  <Pin className="size-3 fill-current" />
                  Đã ghim
                </Badge>
              ) : null}

             <div className="space-y-1">
               <div className="flex items-center justify-between gap-2">
                 <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                   Nội dung
                 </p>
                 {note.created_at ? (
                   <span className="flex items-center gap-1 text-xs text-muted-foreground">
                     <Clock className="size-3" /> {formatNoteTime(note.created_at)}
                   </span>
                 ) : null}
               </div>
               <p className="whitespace-pre-wrap break-words text-sm">
                  {parsedBody.baseText || (parsedBody.reflections.length === 0 ? 'Chưa có nội dung.' : '')}
               </p>
                {parsedBody.reflections.length > 0 ? (
                  <div className="space-y-2 pt-2">
                    {parsedBody.reflections.map((refl, idx) => (
                     <div
                       key={refl.id}
                       data-testid="note-reflection-box-detail"
                       className="rounded-md border border-warn/30 bg-warn-bg p-3 text-xs text-foreground space-y-1.5 shadow-sm"
                     >
                        <div className="flex flex-wrap items-center justify-between gap-1 text-xs font-bold text-foreground">
                          <span className="flex flex-wrap items-center gap-1">
                            <span>💬 Lời nhắn từ tương lai</span>
                            <span className="font-semibold text-muted-foreground">({refl.time})</span>
                          </span>
                          <div className="flex items-center gap-1">
                            <Button
                              size="icon-xs"
                              variant="ghost"
                              className="size-8 min-h-8 min-w-8 p-0 hover:bg-warn/20"
                              aria-label="Sửa lời nhắn"
                              onClick={() => {
                                setEditingReflectionIdx(idx)
                                setEditingReflectionText(refl.text)
                              }}
                            >
                              <Pencil className="size-3" />
                            </Button>
                            <Button
                              size="icon-xs"
                              variant="ghost"
                              className="size-8 min-h-8 min-w-8 p-0 text-bad hover:bg-warn/20 hover:text-bad"
                              aria-label="Xoá lời nhắn"
                              onClick={() => {
                                const newBody = deleteFutureReflection(note.body_md, idx)
                                update.mutate({ body_md: newBody })
                              }}
                            >
                              <Trash2 className="size-3" />
                            </Button>
                          </div>
                        </div>
                        <p className="whitespace-pre-wrap break-words text-xs text-foreground">
                          {refl.text}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : null}
             </div>

              <div className="space-y-3">
                <div>
                  <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Checklist
                  </p>
                  {note.items.length > 0 ? (
                    <p className="mt-1 text-xs text-muted-foreground">
                      {completedItems}/{note.items.length} mục đã xong
                    </p>
                  ) : null}
                </div>

               {note.items.length === 0 ? (
                 <p className="text-sm text-muted-foreground">Chưa có mục nhỏ.</p>
               ) : (
                 <div className="space-y-2">
                   {note.items.map((item, index) => (
                     <div
                        className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 sm:gap-2 rounded-md bg-muted/40 p-2 sm:px-2.5 sm:py-1.5"
                        data-testid="note-item"
                        data-note-item-id={item.id}
                        key={item.id}
                      >
                        {editingItemId === item.id ? (
                          <>
                            <Input
                              data-testid="note-item-edit-input"
                              className="h-10 min-w-0 flex-1 bg-card"
                              aria-label={`Sửa mục ${item.content}`}
                              value={editingItemContent}
                              onChange={(event) => setEditingItemContent(event.target.value)}
                            />
                            <Button
                              data-testid="note-item-edit-save"
                              size="lg"
                              disabled={!editingItemContent.trim() || changeItem.isPending}
                              onClick={() =>
                                changeItem.mutate({
                                  item,
                                  changes: { content: editingItemContent.trim() },
                                })
                              }
                            >
                              Lưu
                            </Button>
                          </>
                        ) : (
                          <>
                            <div className="flex min-w-0 flex-1 items-start sm:items-center gap-2.5">
                            <Checkbox
                              data-testid="note-item-checkbox"
                              aria-label={`Đánh dấu ${item.content} hoàn thành`}
                              checked={item.is_completed}
                              className="mt-0.5 sm:mt-0"
                              disabled={changeItem.isPending}
                              onCheckedChange={(checked) =>
                                changeItem.mutate({
                                  item,
                                  changes: { is_completed: checked === true },
                                })
                              }
                            />
                            <span
                              data-testid="note-item-content"
                              className={`min-w-0 flex-1 break-words text-sm ${
                                item.is_completed ? 'text-muted-foreground line-through' : ''
                              }`}
                            >
                              {item.content}
                            </span>
                            </div>
                            <div className="flex shrink-0 items-center justify-end gap-1 self-end sm:self-auto pt-1 sm:pt-0">
                            <Button
                              data-testid="note-item-up"
                              size="icon-lg"
                              variant="ghost"
                              className="size-11 min-h-11 min-w-11 sm:size-8 sm:min-h-8 sm:min-w-8"
                              aria-label={`Đưa ${item.content} lên`}
                              disabled={index === 0 || reorderItems.isPending}
                              onClick={() => moveItem(index, -1)}
                            >
                              <ArrowUp />
                            </Button>
                            <Button
                              data-testid="note-item-down"
                              size="icon-lg"
                              variant="ghost"
                              className="size-11 min-h-11 min-w-11 sm:size-8 sm:min-h-8 sm:min-w-8"
                              aria-label={`Đưa ${item.content} xuống`}
                              disabled={index === note.items.length - 1 || reorderItems.isPending}
                              onClick={() => moveItem(index, 1)}
                            >
                              <ArrowDown />
                            </Button>
                            <Button
                              data-testid="note-item-edit"
                              size="icon-lg"
                              variant="ghost"
                              className="size-11 min-h-11 min-w-11 sm:size-8 sm:min-h-8 sm:min-w-8"
                              aria-label={`Sửa mục ${item.content}`}
                              onClick={() => startEditingItem(item)}
                            >
                              <Edit3 />
                            </Button>
                            <Button
                              data-testid="note-item-delete"
                              size="icon-lg"
                              variant="ghost"
                              className="size-11 min-h-11 min-w-11 sm:size-8 sm:min-h-8 sm:min-w-8 text-bad hover:text-bad"
                              aria-label={`Xoá mục ${item.content}`}
                              disabled={removeItem.isPending}
                              onClick={() => removeItem.mutate(item)}
                            >
                              <Trash2 />
                            </Button>
                            </div>
                          </>
                        )}
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
                    data-testid="note-item-add-input"
                    aria-label={`Thêm checklist cho ${label}`}
                    className="h-10 bg-card"
                    placeholder="Thêm checklist…"
                    value={newItem}
                    onChange={(event) => setNewItem(event.target.value)}
                  />
                  <Button
                    data-testid="note-item-add-submit"
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
                <Button
                  variant="outline"
                  size="lg"
                  onClick={() => {
                    setDetailsOpen(false)
                    setReflectionOpen(true)
                  }}
                >
                  <Sparkles data-icon="inline-start" className="text-primary" />
                  Lời nhắn từ tương lai
                </Button>
                <Button size="lg" onClick={() => setEditing(true)}>
                  <Edit3 data-icon="inline-start" />
                  Sửa ghi chú
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

          {mutationError ? <p className="text-sm text-bad">{errorMessage(mutationError)}</p> : null}
        </DialogContent>
      </Dialog>

      <Dialog open={reflectionOpen} onOpenChange={setReflectionOpen}>
        <DialogContent
          data-testid="note-future-reflection-dialog"
          className="max-h-[85vh] overflow-y-auto sm:max-w-lg"
        >
          <DialogHeader>
            <DialogTitle>Lời nhắn từ tương lai · {label}</DialogTitle>
            <DialogDescription>
              Gửi cập nhật, suy nghĩ hoặc phản hồi thực tế vào ghi chú này sau một thời gian trải nghiệm.
            </DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              const trimmed = reflectionText.trim()
              if (!trimmed || update.isPending) return
              const newBody = appendFutureReflection(note.body_md, trimmed)
              update.mutate(
                { body_md: newBody },
                {
                  onSuccess: () => {
                    setReflectionText('')
                    setReflectionOpen(false)
                    toast.success(`Đã thêm lời nhắn từ tương lai cho "${label}"`)
                  },
                },
              )
            }}
          >
            <div className="space-y-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Nội dung lời nhắn
              </label>
              <Textarea
                data-testid="note-future-reflection-input"
                className="min-h-28 bg-card text-sm"
                placeholder="Ví dụ: Sau 1 tháng xem lại, thực tế là ta đã hoàn thành việc này và có thêm công cụ mới..."
                value={reflectionText}
                onChange={(e) => setReflectionText(e.target.value)}
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setReflectionOpen(false)}
              >
                Huỷ
              </Button>
              <Button
                data-testid="note-future-reflection-submit"
                type="submit"
                disabled={!reflectionText.trim() || update.isPending}
              >
                <Sparkles data-icon="inline-start" className="size-4" />
                {update.isPending ? 'Đang gửi…' : 'Gửi lời nhắn'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={editingReflectionIdx !== null}
        onOpenChange={(open) => !open && setEditingReflectionIdx(null)}
      >
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Sửa lời nhắn từ tương lai · {label}</DialogTitle>
            <DialogDescription>
              Cập nhật nội dung lời nhắn này.
            </DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              if (editingReflectionIdx === null) return
              const trimmed = editingReflectionText.trim()
              if (!trimmed || update.isPending) return
              const newBody = updateFutureReflection(note.body_md, editingReflectionIdx, trimmed)
              update.mutate(
                { body_md: newBody },
                {
                  onSuccess: () => {
                    setEditingReflectionIdx(null)
                    setEditingReflectionText('')
                    toast.success('Đã sửa lời nhắn từ tương lai')
                  },
                },
              )
            }}
          >
            <div className="space-y-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Nội dung lời nhắn
              </label>
              <Textarea
                className="min-h-28 bg-card text-sm"
                value={editingReflectionText}
                onChange={(e) => setEditingReflectionText(e.target.value)}
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setEditingReflectionIdx(null)}
              >
                Huỷ
              </Button>
              <Button type="submit" disabled={!editingReflectionText.trim() || update.isPending}>
                {update.isPending ? 'Đang lưu…' : 'Lưu thay đổi'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
     </>
   )
 })

export function NotesScreen() {
  const queryClient = useQueryClient()
  const quickInputRef = useRef<HTMLInputElement>(null)
  const [quickTitle, setQuickTitle] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [sortMode, setSortMode] = useState<NoteSortMode>(() => {
    try {
      const stored = window.localStorage.getItem('microsched_notes_sort_mode')
      if (stored === 'alphabet' || stored === 'created' || stored === 'updated') {
        return stored
      }
    } catch {
      // ignore storage access errors
    }
    return 'alphabet'
  })

  function handleSortChange(mode: NoteSortMode) {
    setSortMode(mode)
    try {
      window.localStorage.setItem('microsched_notes_sort_mode', mode)
    } catch {
      // ignore storage write errors
    }
  }

  const notes = useQuery({
    queryKey: noteQueryKey,
    queryFn: () =>
      fetchAllNotes((limit, offset) =>
        apiRequest<{ items: Note[] }>(`/api/notes?limit=${limit}&offset=${offset}`),
      ),
    refetchInterval: standardRefetchInterval,
    retry: (failureCount, error) =>
      !(error instanceof UnauthenticatedError) &&
      !(error instanceof NotePageLimitError) &&
      failureCount < 2,
  })

  const sortedNotes = useMemo(
    () => sortNotes(notes.data ?? [], sortMode),
    [notes.data, sortMode],
  )

  const create = useMutation({
    mutationFn: ({ payload }: { payload: NotePayload; source: CreateSource }) =>
      apiRequest<Note>('/api/notes', {
        method: 'POST',
        body: JSON.stringify({ ...payload, items: [] }),
      }),
    onSuccess: (_note, variables) => {
      if (variables.source === 'quick') {
        setQuickTitle('')
        window.requestAnimationFrame(() => quickInputRef.current?.focus())
      } else {
        setCreateOpen(false)
      }
      void queryClient.invalidateQueries({ queryKey: noteInvalidationKey })
    },
  })

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
        is_private: false,
      },
    })
  }

  return (
    <div className="space-y-4">
      <section aria-labelledby="quick-add-note-heading">
        <h2 className="sr-only" id="quick-add-note-heading">
          Thêm ghi chú
        </h2>
        <form className="flex gap-2" onSubmit={quickAdd}>
          <Input
            data-testid="quick-add-note-input"
            ref={quickInputRef}
            className="h-11 flex-1 rounded-lg bg-card px-4 shadow-1"
            aria-label="Thêm ghi chú nhanh"
            placeholder="Thêm ghi chú rồi lưu…"
            value={quickTitle}
            onChange={(event) => setQuickTitle(event.target.value)}
          />
          <Button
            data-testid="quick-add-note-submit"
            className="h-11 rounded-lg px-5"
            size="lg"
            type="submit"
            disabled={!quickTitle.trim() || create.isPending}
          >
            {create.isPending ? 'Đang thêm…' : 'Thêm'}
          </Button>
        </form>

        {create.isError && create.variables?.source === 'quick' ? (
          <p className="mt-2 px-1 text-sm text-bad" role="alert">
            {errorMessage(create.error)}
          </p>
        ) : null}

        <div className="mt-2 px-1">
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button className="h-auto px-0 py-1 text-xs" size="sm" variant="link">
                <Plus data-icon="inline-start" />
                Thêm chi tiết
              </Button>
            </DialogTrigger>
            <DialogContent
              data-testid="note-create-dialog"
              className="max-h-[85vh] overflow-y-auto sm:max-w-lg"
            >
              <DialogHeader>
                <DialogTitle>Tạo ghi chú</DialogTitle>
                <DialogDescription>
                  Tiêu đề không bắt buộc; thêm nội dung hoặc chế độ riêng tư.
                </DialogDescription>
              </DialogHeader>
              <NoteForm
                submitLabel="Tạo ghi chú"
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
                Ghi chú riêng tư sẽ được mã hoá và chỉ hiện khi private unlock đang mở.
              </p>
            </DialogContent>
          </Dialog>
        </div>
      </section>

      <section aria-labelledby="note-list-heading" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-bold" id="note-list-heading">
            Danh sách ghi chú
          </h2>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Sắp xếp:</span>
            <Select value={sortMode} onValueChange={(val) => handleSortChange(val as NoteSortMode)}>
              <SelectTrigger data-testid="note-sort" size="sm" className="w-[160px] bg-card text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent align="end">
                <SelectItem value="alphabet">Bảng chữ cái</SelectItem>
                <SelectItem value="created">Thời gian tạo</SelectItem>
                <SelectItem value="updated">Thời gian sửa</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {notes.isPending ? (
          <p className="text-sm text-muted-foreground">Đang tải ghi chú…</p>
        ) : null}
        {notes.isError ? (
          notes.error instanceof NotePageLimitError ? (
            <div data-testid="note-page-limit-error" className="flex flex-wrap items-center gap-3">
              <p className="text-sm text-bad">Không tải đủ ghi chú để sắp xếp. Thử lại.</p>
              <Button variant="outline" size="lg" onClick={() => void notes.refetch()}>
                Thử lại
              </Button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <p className="text-sm text-bad">{errorMessage(notes.error)}</p>
              <Button variant="outline" size="lg" onClick={() => void notes.refetch()}>
                Thử lại
              </Button>
            </div>
          )
        ) : null}
        {notes.data && notes.data.length === 0 ? (
          <Card className="rounded-lg border border-dashed bg-transparent p-6 text-center text-sm text-muted-foreground shadow-none">
            Chưa có ghi chú.
          </Card>
        ) : null}

        <div data-testid="note-list" className="space-y-3">
          {sortedNotes.map((note) => <NoteCard note={note} key={note.id} />)}
        </div>
      </section>
    </div>
  )
}
