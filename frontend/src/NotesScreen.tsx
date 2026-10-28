import {
  type FormEvent,
  type MouseEvent,
  type KeyboardEvent,
  memo,
  useMemo,
  useRef,
  useState,
} from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  ArrowUpToLine,
  Clock,
  Edit3,
  Pencil,
  Pin,
  Plus,
  Sparkles,
  Trash2,
} from 'lucide-react'
import { toast } from 'sonner'

import { apiRequest, UnauthenticatedError } from '@/api'
import { commitOutcomeMessage } from '@/acknowledgement'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { NoteChecklist } from '@/NoteChecklist'
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
import { PrivateMarker } from '@/PrivateMarker'
import { PRIVATE_SURFACE_CLASS } from '@/private-presentation'
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
  const [expanded, setExpanded] = useState(false)
  const [deletingItem, setDeletingItem] = useState<NoteItem | null>(null)
  const [deletingReflection,setDeletingReflection]=useState<number|null>(null)
  const [editing, setEditing] = useState(false)
  const [newItem, setNewItem] = useState('')
  const [reflectionOpen, setReflectionOpen] = useState(false)
  const [reflectionText, setReflectionText] = useState('')
  const [editingItemId, setEditingItemId] = useState<string | null>(null)
  const [editingItemContent, setEditingItemContent] = useState('')
  const newItemRevision = useRef(0)
  const editDraft = useRef({ id: '', revision: 0 })
  const addInFlight = useRef(false)
  const editInFlight = useRef(false)
  const addComposing = useRef(false)
  const editComposing = useRef(false)
  const [editingReflectionIdx, setEditingReflectionIdx] = useState<number | null>(null)
  const [editingReflectionText, setEditingReflectionText] = useState('')
  const parsedBody = useMemo(() => parseNoteBody(note.body_md), [note.body_md])
  const detailsReturnRef = useRef<HTMLButtonElement | null>(null)
  const detailsReturnTop = useRef<number | null>(null)
  const readerRef = useRef<HTMLDivElement>(null)
  const readerHeaderRef = useRef<HTMLDivElement>(null)
  const moveInFlight = useRef(false)
  const moveFocus = useRef<Element | null>(null)
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
    mutationFn: ({ content }: { content: string; revision: number }) =>
      apiRequest<NoteItem>(`/api/notes/${note.id}/items`, {
        method: 'POST',
        body: JSON.stringify({ content, position: note.items.length }),
      }),
    onSuccess: (_data, variables) => {
      if (newItemRevision.current === variables.revision) {
        newItemRevision.current += 1
        setNewItem('')
      }
      refresh()
    },
    onSettled: () => { addInFlight.current = false },
  })
  const changeItem = useMutation({
    mutationFn: ({ item, changes }: { item: NoteItem; changes: Partial<NoteItem>; draftRevision?: number }) =>
      apiRequest<NoteItem>(`/api/notes/${note.id}/items/${item.id}`, {
        method: 'PATCH',
        body: JSON.stringify(changes),
      }),
    onSuccess: (_data, variables) => {
      if (variables.changes.content !== undefined && editDraft.current.id === variables.item.id && editDraft.current.revision === variables.draftRevision) {
        editDraft.current = { id: '', revision: editDraft.current.revision + 1 }
        setEditingItemId(null)
        setEditingItemContent('')
      }
      refresh()
    },
    onSettled: () => { editInFlight.current = false },
  })
  const reorderItems = useMutation({
    mutationFn: ({ item, expectedItems }: { item: NoteItem; expectedItems: Pick<NoteItem, 'id' | 'position' | 'is_completed'>[] }) => apiRequest<NoteItem[]>(
      `/api/notes/${note.id}/items/${item.id}/move-to-top`, {
        method: 'POST',
        body: JSON.stringify({ expected_items: expectedItems }),
      }),
    onSuccess: (items, { item }) => {
      // Update only an existing visible note; never resurrect a cache removed by lock/logout.
      queryClient.setQueryData<Note[]>(noteQueryKey, old => old?.map(entry => entry.id === note.id ? { ...entry, items } : entry))
      refresh()
      requestAnimationFrame(() => {
        const reader = readerRef.current
        if (!reader || (document.activeElement !== document.body && document.activeElement !== moveFocus.current)) return
        const row = reader.querySelector<HTMLElement>(`[data-note-item-id="${item.id}"]`)
        if (!row) return
        const control = row.querySelector<HTMLButtonElement>('[data-testid="note-item-edit"]')
        if (!control) return
        const headerBottom = readerHeaderRef.current?.getBoundingClientRect().bottom ?? 0
        if (control.getBoundingClientRect().top < headerBottom || control.getBoundingClientRect().bottom > reader.getBoundingClientRect().bottom) {
          reader.scrollTop += control.getBoundingClientRect().top - headerBottom - 16
        }
        control.focus({ preventScroll: true })
      })
    },
    onError: refresh,
    onSettled: () => { moveInFlight.current = false },
  })
  const removeItem = useMutation({
    mutationFn: (item: NoteItem) =>
      apiRequest<void>(`/api/notes/${note.id}/items/${item.id}`, { method: 'DELETE' }),
    onSuccess: () => { setDeletingItem(null); refresh() },
  })

  const completedItems = note.items.filter((item) => item.is_completed).length
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
    detailsReturnTop.current = event.currentTarget.getBoundingClientRect().top
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
        'button, a, input, textarea, select, label, [role="button"], [contenteditable="true"], [data-testid="note-item-content"]',
      )
    ) {
      return
    }
    const title = event.currentTarget.querySelector<HTMLButtonElement>(
      '[data-testid="note-title"]',
    )
    if (!title) return
    detailsReturnRef.current = title
    detailsReturnTop.current = title.getBoundingClientRect().top
    setEditing(false)
    setDetailsOpen(true)
  }

  function openEditor(event: MouseEvent<HTMLButtonElement>) {
    detailsReturnRef.current = event.currentTarget
    detailsReturnTop.current = event.currentTarget.getBoundingClientRect().top
    setEditing(true)
    setDetailsOpen(true)
  }

  function startEditingItem(item: NoteItem) {
    editDraft.current = { id: item.id, revision: editDraft.current.revision + 1 }
    setEditingItemId(item.id)
    setEditingItemContent(item.content)
  }

  function submitNewItem() {
    const content = newItem.trim()
    if (!content || addItem.isPending || addInFlight.current || addComposing.current) return
    addInFlight.current = true
    addItem.mutate({ content, revision: newItemRevision.current })
  }

  function submitEditedItem(item: NoteItem) {
    const content = editingItemContent.trim()
    if (!content || changeItem.isPending || editInFlight.current || editComposing.current) return
    editInFlight.current = true
    changeItem.mutate({ item, changes: { content }, draftRevision: editDraft.current.revision })
  }

  function checklistKey(event: KeyboardEvent<HTMLTextAreaElement>, submit: () => void) {
    if (event.key !== 'Enter' || !event.ctrlKey) return
    event.preventDefault()
    if (event.repeat || event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return
    submit()
  }

  function moveItem(item: NoteItem) {
    const group = note.items.filter((entry) => entry.is_completed === item.is_completed)
    if (group[0]?.id === item.id || moveInFlight.current || changeItem.isPending || editingItemId) return
    moveInFlight.current = true
    moveFocus.current = document.activeElement
    reorderItems.mutate({ item, expectedItems: note.items.map(({ id, position, is_completed }) => ({ id, position, is_completed })) })
  }

  function jumpToSection(name: string) {
    const reader = readerRef.current
    const section = reader?.querySelector<HTMLElement>(`[data-reader-section="${name}"]`)
    if (!reader || !section) return
    reader.scrollTop += section.getBoundingClientRect().top - reader.getBoundingClientRect().top - (readerHeaderRef.current?.offsetHeight ?? 0) - 16
    section.focus({ preventScroll: true })
  }

  return (
    <>
      <Card
        data-testid="note-card"
        data-note-id={note.id}
        data-private={note.is_private}
        onClick={openDetailsFromCard}
        className={cn('gap-3 overflow-visible rounded-lg bg-card px-4 py-4 shadow-2 ring-0 transition-shadow', note.is_private && PRIVATE_SURFACE_CLASS)}
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
                className="h-auto min-h-11 min-w-0 shrink justify-start whitespace-normal [overflow-wrap:anywhere] p-0 text-left text-base font-bold tracking-tight hover:bg-transparent"
                variant="ghost"
                aria-label={`Mở chi tiết ${label}`}
                onClick={openDetails}
              >
                {label}
              </Button>
              {note.is_private ? (
                <PrivateMarker testId="note-private-badge-card" />
              ) : null}
              </div>
            </div>

            {parsedBody.baseText ? (
              <p data-testid="note-body-preview" className={cn("whitespace-pre-wrap [overflow-wrap:anywhere] text-sm text-muted-foreground w-full",!expanded&&"line-clamp-6")}>
                {parsedBody.baseText}
              </p>
            ) : null}

            {parsedBody.reflections.length > 0 ? (
              <div className="space-y-2 pt-1 w-full">
                {(expanded ? parsedBody.reflections : parsedBody.reflections.slice(0,1)).map((refl, idx) => (
                 <div
                   key={refl.id}
                   data-testid="note-reflection-box"
                   className="rounded-lg border border-reflection-foreground/20 bg-reflection-bg p-3 text-xs text-foreground space-y-2 w-full"
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
                          className="size-8 min-h-8 min-w-8 p-0 hover:bg-reflection-foreground/10"
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
                          className="size-8 min-h-8 min-w-8 p-0 text-bad hover:bg-reflection-foreground/10 hover:text-bad"
                          aria-label="Xoá lời nhắn"
                          onClick={(e) => {
                            e.stopPropagation()
                            setDeletingReflection(idx)
                          }}
                        >
                          <Trash2 className="size-3" />
                        </Button>
                      </div>
                    </div>
                    <p className={cn("whitespace-pre-wrap [overflow-wrap:anywhere] text-xs text-foreground",!expanded&&"line-clamp-4")}>
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
          <NoteChecklist
            key={expanded ? 'full' : 'preview'}
            items={note.items}
            preview={!expanded}
            pending={changeItem.isPending}
            failed={changeItem.isError}
            onToggle={(item, checked) =>
              changeItem.mutate({ item, changes: { is_completed: checked } })
            }
          />
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border/50 pt-2">
          <Button data-testid="note-expand" variant="ghost" className="min-h-11" aria-expanded={expanded} onClick={()=>setExpanded(value=>!value)}>{expanded ? 'Thu gọn' : 'Xem đầy đủ'}</Button>
          <Button data-testid="note-open-full" variant="link" className="min-h-11" aria-label={`Mở chi tiết ${label}`} onClick={openDetails}>Chi tiết & mục nhỏ</Button>
        </div>
        {mutationError ? <p className="text-sm text-bad">{errorMessage(mutationError)}</p> : null}
        {commitOutcomeMessage(reorderItems.error) && reorderItems.variables ? <Button type="button" variant="outline" disabled={reorderItems.isPending} onClick={() => reorderItems.mutate(reorderItems.variables!)}>Thử lại đúng yêu cầu đưa lên đầu</Button> : null}
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
          ref={readerRef}
          data-testid="note-detail-dialog"
          showCloseButton={false}
          className="inset-0 h-dvh max-h-dvh w-full max-w-none translate-x-0 translate-y-0 content-start gap-0 overflow-y-auto overscroll-contain rounded-none p-0 sm:max-w-none"
          onOpenAutoFocus={event => { event.preventDefault(); readerHeaderRef.current?.querySelector<HTMLButtonElement>('button')?.focus({ preventScroll: true }) }}
          onCloseAutoFocus={(event) => {
            const opener = detailsReturnRef.current
            if (!opener?.isConnected) return
            event.preventDefault()
            requestAnimationFrame(() => {
              if (!opener.isConnected) return
              opener.focus({ preventScroll: true })
              if (detailsReturnTop.current !== null) {
                window.scrollBy({ top: opener.getBoundingClientRect().top - detailsReturnTop.current, behavior: 'instant' })
              }
            })
          }}
        >
          <div ref={readerHeaderRef} className="sticky top-0 z-10 border-b bg-card px-4 pb-2 pt-[max(0.5rem,env(safe-area-inset-top))] sm:px-8">
            <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-2">
              <Button variant="ghost" size="lg" data-testid="note-reader-back" onClick={() => { setDetailsOpen(false); setEditing(false); setEditingItemId(null) }}><ArrowLeft aria-hidden="true" />Ghi chú</Button>
              <div className="flex gap-2">
                {!editing ? <Button variant="outline" size="lg" onClick={() => { jumpToSection('checklist'); readerRef.current?.querySelector<HTMLTextAreaElement>('[data-testid="note-item-add-input"]')?.focus() }}><Plus aria-hidden="true" />Thêm mục</Button> : null}
                {!editing ? <Button variant="outline" size="lg" onClick={() => setEditing(true)}><Pencil aria-hidden="true" />Chỉnh sửa</Button> : null}
              </div>
            </div>
            {!editing ? <nav aria-label="Phần ghi chú" className="mx-auto flex max-w-[80ch] flex-wrap gap-1">
              <Button variant="ghost" className="min-h-11" onClick={() => jumpToSection('body')}>Nội dung</Button>
              <Button variant="ghost" className="min-h-11" onClick={() => jumpToSection('checklist')}>Checklist {completedItems}/{note.items.length}</Button>
              <Button variant="ghost" className="min-h-11" onClick={() => jumpToSection('reflections')}>Lời nhắn</Button>
            </nav> : null}
          </div>
          <div className="mx-auto w-full min-w-0 max-w-[80ch] space-y-6 px-4 py-6 pb-[max(2rem,env(safe-area-inset-bottom))] sm:px-8">
          <DialogHeader className="text-left">
            <DialogTitle className="pr-0 text-2xl leading-tight [overflow-wrap:anywhere] sm:text-3xl">{editing ? `Sửa · ${label}` : label}</DialogTitle>
            <DialogDescription>{editing ? 'Cập nhật nội dung hoặc chế độ riêng tư.' : `${completedItems}/${note.items.length} mục đã xong`}</DialogDescription>
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
            <div className="min-w-0 space-y-5">
              {note.is_private ? (
                <PrivateMarker testId="note-private-badge-detail" />
              ) : null}
              {note.pinned ? (
                <Badge data-testid="note-pinned-badge-detail" variant="default" className="gap-1">
                  <Pin className="size-3 fill-current" />
                  Đã ghim
                </Badge>
              ) : null}

             <section data-reader-section="body" tabIndex={-1} className="space-y-1 outline-none">
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
               <p className="whitespace-pre-wrap [overflow-wrap:anywhere] text-base leading-relaxed">
                  {parsedBody.baseText || 'Chưa có nội dung.'}
               </p>

             </section>

              <section data-reader-section="checklist" tabIndex={-1} className="space-y-3 border-t pt-6 outline-none">
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
                 <NoteChecklist
                   items={note.items}
                   pending={changeItem.isPending}
                   failed={changeItem.isError}
                   onToggle={(item, checked) =>
                     changeItem.mutate({ item, changes: { is_completed: checked } })
                   }
                   renderItem={(item, toggle) => {
                     const group = note.items.filter((entry) => entry.is_completed === item.is_completed)
                     const index = group.findIndex((entry) => entry.id === item.id)
                     return (
                     <div className="min-w-0 space-y-2 border-b border-border/60 py-3">
                        {editingItemId === item.id ? (
                          <>
                            <div className="min-w-0 flex-1 space-y-1">
                              <Textarea
                                data-testid="note-item-edit-input"
                                data-update-dirty={editingItemId !== null || undefined}
                                rows={2}
                                className="min-h-20 min-w-0 resize-y bg-card"
                                aria-label={`Sửa mục ${item.content}`}
                                aria-describedby={`note-edit-hint-${note.id}`}
                                value={editingItemContent}
                                onChange={event => { editDraft.current.revision += 1; setEditingItemContent(event.target.value) }}
                                onCompositionStart={() => { editComposing.current = true }}
                                onCompositionEnd={() => { editComposing.current = false }}
                                onKeyDown={event => checklistKey(event, () => submitEditedItem(item))}
                              />
                              <p id={`note-edit-hint-${note.id}`} className="text-xs text-muted-foreground">Enter xuống dòng · Ctrl+Enter lưu</p>
                            </div>
                            <Button data-testid="note-item-edit-save" size="lg"
                              disabled={!editingItemContent.trim() || changeItem.isPending}
                              onClick={() => submitEditedItem(item)}>
                              Lưu
                            </Button>
                          </>
                        ) : (
                          <>
                            <div className="min-w-0 flex-1">{toggle}</div>
                            <div className="flex items-center gap-2 pl-11">
                            <Button
                              data-testid="note-item-edit"
                              size="icon-lg"
                              variant="ghost"
                              className="size-11 min-h-11 min-w-11"
                              title="Sửa mục"
                              aria-label={`Sửa mục ${item.content}`}
                              onClick={() => startEditingItem(item)}
                            >
                              <Pencil aria-hidden="true" />
                            </Button>
                            <Button
                              data-testid="note-item-top"
                              size="icon-lg"
                              variant="outline"
                              className="size-11 min-h-11 min-w-11"
                              title="Đưa lên đầu"
                              aria-label={`Đưa ${item.content} lên đầu`}
                              disabled={index === 0 || reorderItems.isPending || changeItem.isPending || editingItemId !== null}
                              onClick={() => moveItem(item)}
                            ><ArrowUpToLine aria-hidden="true" /></Button>
                            <Button
                              data-testid="note-item-delete"
                              size="icon-lg"
                              variant="ghost"
                              className="size-11 min-h-11 min-w-11 text-bad hover:text-bad"
                              title="Xoá mục"
                              aria-label={`Xoá mục ${item.content}`}
                              disabled={removeItem.isPending}
                              onClick={() => setDeletingItem(item)}
                            >
                              <Trash2 />
                            </Button>
                            </div>
                          </>
                        )}
                      </div>
                     )
                   }}
                 />
                )}

                <form className="space-y-1" onSubmit={event => { event.preventDefault(); submitNewItem() }}>
                  <div className="flex items-start gap-2">
                    <Textarea
                      data-testid="note-item-add-input"
                      rows={2}
                      aria-label={`Thêm checklist cho ${label}`}
                      aria-describedby={`note-add-hint-${note.id}`}
                      className="min-h-20 resize-y bg-card"
                      placeholder="Thêm checklist…"
                      value={newItem}
                      onChange={event => { newItemRevision.current += 1; setNewItem(event.target.value) }}
                      onCompositionStart={() => { addComposing.current = true }}
                      onCompositionEnd={() => { addComposing.current = false }}
                      onKeyDown={event => checklistKey(event, submitNewItem)}
                    />
                    <Button data-testid="note-item-add-submit" size="lg" type="submit" variant="secondary" disabled={!newItem.trim() || addItem.isPending}>
                      <Plus data-icon="inline-start" />Thêm
                    </Button>
                  </div>
                  <p id={`note-add-hint-${note.id}`} className="text-xs text-muted-foreground">Enter xuống dòng · Ctrl+Enter thêm</p>
                </form>
              </section>
              <section data-reader-section="reflections" tabIndex={-1} className="space-y-3 border-t pt-6 outline-none">
                <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Lời nhắn từ tương lai</h3>
                {parsedBody.reflections.length > 0 ? (
                  <div className="space-y-2 pt-2">
                    {parsedBody.reflections.map((refl, idx) => (
                     <div
                       key={refl.id}
                       data-testid="note-reflection-box-detail"
                       className="rounded-lg border border-reflection-foreground/20 bg-reflection-bg p-3 text-xs text-foreground space-y-2"
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
                              className="size-8 min-h-8 min-w-8 p-0 hover:bg-reflection-foreground/10"
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
                              className="size-8 min-h-8 min-w-8 p-0 text-bad hover:bg-reflection-foreground/10 hover:text-bad"
                              aria-label="Xoá lời nhắn"
                              onClick={() => {
                                setDeletingReflection(idx)
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
                {parsedBody.reflections.length === 0 ? <p className="text-sm text-muted-foreground">Chưa có lời nhắn.</p> : null}
              </section>

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
          {commitOutcomeMessage(reorderItems.error) && reorderItems.variables ? <Button type="button" variant="outline" disabled={reorderItems.isPending} onClick={() => reorderItems.mutate(reorderItems.variables!)}>Thử lại đúng yêu cầu đưa lên đầu</Button> : null}
          </div>
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
      <Dialog open={deletingReflection!==null} onOpenChange={open=>{if(!open&&!update.isPending)setDeletingReflection(null)}}><DialogContent data-testid="note-reflection-delete-confirm"><DialogHeader><DialogTitle>Xoá lời nhắn này?</DialogTitle><DialogDescription>Lời nhắn sẽ bị xoá khỏi ghi chú và không thể hoàn tác.</DialogDescription></DialogHeader>{update.isError?<p role="alert" className="text-sm text-bad">{errorMessage(update.error)}</p>:null}<div className="flex justify-end gap-2"><Button size="lg" variant="outline" disabled={update.isPending} onClick={()=>setDeletingReflection(null)}>Huỷ</Button><Button size="lg" variant="destructive" disabled={update.isPending} onClick={()=>{if(deletingReflection!==null)update.mutate({body_md:deleteFutureReflection(note.body_md,deletingReflection)},{onSuccess:()=>setDeletingReflection(null)})}}>{update.isPending?'Đang xoá…':'Xoá lời nhắn'}</Button></div></DialogContent></Dialog>
      <Dialog open={!!deletingItem} onOpenChange={open=>{if(!open&&!removeItem.isPending)setDeletingItem(null)}}><DialogContent data-testid="note-child-delete-confirm"><DialogHeader><DialogTitle>Xoá mục nhỏ?</DialogTitle><DialogDescription>Mục này sẽ bị xoá khỏi ghi chú và không thể hoàn tác.</DialogDescription></DialogHeader><p className="break-words text-sm">{deletingItem?.content}</p>{removeItem.isError?<p role="alert" className="text-sm text-bad">{errorMessage(removeItem.error)}</p>:null}<div className="flex justify-end gap-2"><Button size="lg" variant="outline" disabled={removeItem.isPending} onClick={()=>setDeletingItem(null)}>Huỷ</Button><Button data-testid="note-child-delete-commit" size="lg" variant="destructive" disabled={removeItem.isPending} onClick={()=>{if(deletingItem)removeItem.mutate(deletingItem)}}>{removeItem.isPending?'Đang xoá…':'Xoá mục'}</Button></div></DialogContent></Dialog>
     </>
   )
 })

export function NotesScreen() {
  const queryClient = useQueryClient()
  const quickInputRef = useRef<HTMLInputElement>(null)
  const [quickTitle, setQuickTitle] = useState('')
  const [find, setFind] = useState('')
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

  const visibleNotes = useMemo(() => {
    const query=find.trim().toLocaleLowerCase('vi-VN')
    return query ? sortedNotes.filter(note=>[note.title,note.body_md,...note.items.map(item=>item.content)].some(text=>text?.toLocaleLowerCase('vi-VN').includes(query))) : sortedNotes
  }, [sortedNotes,find])

  const create = useMutation({
    mutationFn: ({ payload }: { payload: NotePayload; source: CreateSource }) =>
      apiRequest<Note>('/api/notes', {
        method: 'POST',
        body: JSON.stringify({ ...payload, items: [] }),
      }),
    onSuccess: (_note, variables) => {
      if (variables.source === 'quick') {
        const submittedTitle = variables.payload.title
        setQuickTitle((current) => (current === submittedTitle || current.trim() === submittedTitle ? '' : current))
        window.requestAnimationFrame(() => quickInputRef.current?.focus({ preventScroll: true }))
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
        {!notes.isError && notes.data && notes.data.length === 0 ? (
          <Card className="rounded-lg border border-dashed bg-transparent p-6 text-center text-sm text-muted-foreground shadow-none">
            Chưa có ghi chú.
          </Card>
        ) : null}

        {!notes.isError ? (
          <><Input data-testid="note-find" type="search" name="note-find" aria-label="Tìm trong ghi chú đã tải" placeholder="Tìm ghi chú…" className="min-h-11 bg-card" value={find} onChange={event=>setFind(event.target.value)}/>
          {find.trim()&&visibleNotes.length===0?<p role="status" className="text-sm text-muted-foreground">Không có ghi chú phù hợp.</p>:null}
          <div data-testid="note-list" className="grid grid-cols-1 items-start gap-3 lg:grid-cols-2">
            {visibleNotes.map((note) => <NoteCard note={note} key={note.id} />)}
          </div></>
        ) : null}
      </section>
    </div>
  )
}
