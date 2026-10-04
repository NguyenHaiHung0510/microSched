import { type ReactNode, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'
import { type NoteItem } from '@/note-ui'

type Props = {
  items: NoteItem[]
  pending: boolean
  failed?: boolean
  preview?: boolean
  onToggle: (item: NoteItem, checked: boolean) => void
  renderItem?: (item: NoteItem, toggle: ReactNode) => ReactNode
}

/** Group only for display: stored positions and explicit reorder actions stay intact. */
export function NoteChecklist({ items, pending, failed = false, preview = false, onToggle, renderItem }: Props) {
  const [remainingExpanded, setRemainingExpanded] = useState(false)
  const [completedExpanded, setCompletedExpanded] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const completedRef = useRef<HTMLButtonElement>(null)
  const focusAfterToggle = useRef<{
    id: string
    checked: boolean
    element: Element | null
    neighborId: string | null
  } | null>(null)
  const scrollAnchor = useRef<{
    container: HTMLElement | null
    isWindow: boolean
    anchorId: string
    offset: number
  } | null>(null)
  const id = useId()
  const remaining = items.filter((item) => !item.is_completed)
  const completed = items.filter((item) => item.is_completed)
  const hiddenRemaining = preview ? Math.max(0, remaining.length - 3) : 0

  useLayoutEffect(() => {
    const anchor = scrollAnchor.current
    if (!anchor) return
    const row = rootRef.current?.querySelector<HTMLElement>(`[data-note-item-id="${anchor.anchorId}"]`)
    if (row && !row.closest('[hidden]')) {
      const rect = row.getBoundingClientRect()
      const containerTop = anchor.container ? anchor.container.getBoundingClientRect().top : 0
      const currentOffset = rect.top - containerTop
      const delta = currentOffset - anchor.offset
      if (Math.abs(delta) > 1) {
        if (anchor.container) {
          anchor.container.scrollTop += delta
        } else if (anchor.isWindow && typeof window !== 'undefined') {
          window.scrollBy({ top: delta, behavior: 'instant' as ScrollBehavior })
        }
      }
    }
    if (!pending) {
      scrollAnchor.current = null
    }
  }, [items, pending])

  useEffect(() => {
    const focus = focusAfterToggle.current
    if (!focus || pending) return
    // Do not steal focus if the user has moved to another control while saving.
    const active = document.activeElement
    if (active && active !== focus.element && active !== document.body) {
      if (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || (active as HTMLElement).isContentEditable) {
        focusAfterToggle.current = null
        return
      }
      focusAfterToggle.current = null
      return
    }
    const rows = Array.from(rootRef.current?.querySelectorAll<HTMLElement>('[data-note-item-id]') ?? [])
    const row = rows.find((element) => element.dataset.noteItemId === focus.id)
    if (row && !row.closest('[hidden]')) {
      row.querySelector<HTMLButtonElement>('[role="checkbox"]')?.focus({ preventScroll: true })
    } else if (!preview && focus.neighborId) {
      const neighbor = rows.find((element) => element.dataset.noteItemId === focus.neighborId)
      if (neighbor && !neighbor.closest('[hidden]')) {
        neighbor.querySelector<HTMLButtonElement>('[role="checkbox"]')?.focus({ preventScroll: true })
      } else {
        completedRef.current?.focus({ preventScroll: true })
      }
    } else {
      completedRef.current?.focus({ preventScroll: true })
    }
    focus.element = document.activeElement
    if (failed || items.find((item) => item.id === focus.id)?.is_completed === focus.checked) {
      focusAfterToggle.current = null
    }
  }, [items, pending, failed])

  function renderRow(item: NoteItem, hidden: boolean) {
    const toggle = (
      <div className="flex min-w-0 items-start gap-1 text-sm">
        <label
          data-testid="note-item-toggle"
          className={cn(
            'inline-flex size-11 shrink-0 cursor-pointer items-center justify-center rounded-md',
            pending && 'cursor-wait opacity-50',
          )}
        >
        <Checkbox
          data-testid="note-item-checkbox"
          aria-label={`Đánh dấu ${item.content} hoàn thành`}
          checked={item.is_completed}
          disabled={pending}
          className="after:inset-0"
          onCheckedChange={(checked) => {
            const dialogContainer = rootRef.current?.closest<HTMLElement>('[data-testid="note-detail-dialog"]')
            const containerTop = dialogContainer ? dialogContainer.getBoundingClientRect().top : 0
            const visibleRows = Array.from(rootRef.current?.querySelectorAll<HTMLElement>('[data-note-item-id]') ?? [])
              .filter((el) => !el.closest('[hidden]') && el.dataset.noteItemId !== item.id)
            const unaffected = visibleRows.find((el) => el.getBoundingClientRect().bottom > containerTop + 10)
            if (unaffected && unaffected.dataset.noteItemId) {
              scrollAnchor.current = {
                container: dialogContainer ?? null,
                isWindow: !dialogContainer,
                anchorId: unaffected.dataset.noteItemId,
                offset: unaffected.getBoundingClientRect().top - containerTop,
              }
            }
            const currentGroup = item.is_completed ? completed : remaining
            const itemIdx = currentGroup.findIndex((entry) => entry.id === item.id)
            const neighbor = currentGroup[itemIdx + 1] ?? currentGroup[itemIdx - 1] ?? null
            focusAfterToggle.current = {
              id: item.id,
              checked: checked === true,
              element: document.activeElement,
              neighborId: neighbor?.id ?? null,
            }
            if (checked !== true) setRemainingExpanded(true)
            onToggle(item, checked === true)
          }}
        />
        </label>
        <span
          data-testid="note-item-content"
          className={cn('min-w-0 py-2.5 whitespace-pre-wrap break-words [overflow-wrap:anywhere]', item.is_completed && 'text-muted-foreground line-through')}
        >
          {item.content}
        </span>
      </div>
    )
    return (
      <div data-testid="note-item" data-note-item-id={item.id} key={item.id} hidden={hidden}>
        {renderItem ? renderItem(item, toggle) : toggle}
      </div>
    )
  }

  return (
    <div data-testid="note-checklist" className="min-w-0 space-y-2" ref={rootRef}>
      <p key="remaining-heading" className="text-xs font-semibold text-muted-foreground">
        Còn lại ({remaining.length})
      </p>
      {remaining.map((item, index) => renderRow(item, preview && !remainingExpanded && index >= 3))}
      {hiddenRemaining > 0 ? (
        <Button
          key="remaining-disclosure"
          data-testid="note-items-remaining-toggle"
          variant="link"
          size="lg"
          className="h-auto px-1 text-xs"
          aria-expanded={remainingExpanded}
          onClick={() => setRemainingExpanded((current) => !current)}
        >
          {remainingExpanded ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}
          {remainingExpanded ? 'Thu gọn mục còn lại' : `+ ${hiddenRemaining} mục khác…`}
        </Button>
      ) : null}
      {completed.length > 0 ? (
        <Button
          key="completed-disclosure"
          ref={completedRef}
          data-testid="note-items-completed-toggle"
          variant="ghost"
          size="lg"
          className="h-auto justify-start px-1 text-xs text-muted-foreground"
          aria-expanded={completedExpanded}
          aria-controls={`${id}-completed`}
          onClick={() => setCompletedExpanded((current) => !current)}
        >
          {completedExpanded ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}
          Đã xong ({completed.length})
        </Button>
      ) : null}
      <div id={`${id}-completed`} hidden={!completedExpanded} className="space-y-2">
        {completed.map((item) => renderRow(item, false))}
      </div>
    </div>
  )
}
