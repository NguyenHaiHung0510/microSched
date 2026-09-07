import { type ReactNode, useEffect, useId, useRef, useState } from 'react'
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
  const focusAfterToggle = useRef<{ id: string; checked: boolean; element: Element | null } | null>(null)
  const id = useId()
  const remaining = items.filter((item) => !item.is_completed)
  const completed = items.filter((item) => item.is_completed)
  const hiddenRemaining = preview ? Math.max(0, remaining.length - 3) : 0

  useEffect(() => {
    const focus = focusAfterToggle.current
    if (!focus || pending) return
    // Do not steal focus if the user has moved to another control while saving.
    if (document.activeElement !== focus.element && document.activeElement !== document.body) {
      focusAfterToggle.current = null
      return
    }
    const row = Array.from(rootRef.current?.querySelectorAll<HTMLElement>('[data-note-item-id]') ?? [])
      .find((element) => element.dataset.noteItemId === focus.id)
    if (row && !row.closest('[hidden]')) row.querySelector<HTMLButtonElement>('[role="checkbox"]')?.focus()
    else completedRef.current?.focus()
    focus.element = document.activeElement
    if (failed || items.find((item) => item.id === focus.id)?.is_completed === focus.checked) {
      focusAfterToggle.current = null
    }
  }, [items, pending, failed])

  function renderRow(item: NoteItem, hidden: boolean) {
    const toggle = (
      <label
        data-testid="note-item-toggle"
        className={cn(
          'inline-flex min-h-11 w-fit max-w-full cursor-pointer items-start gap-2.5 rounded-md px-1 py-2 text-sm',
          pending && 'cursor-wait opacity-50',
        )}
      >
        <Checkbox
          data-testid="note-item-checkbox"
          aria-label={`Đánh dấu ${item.content} hoàn thành`}
          checked={item.is_completed}
          disabled={pending}
          className="mt-1 after:inset-0"
          onCheckedChange={(checked) => {
            focusAfterToggle.current = { id: item.id, checked: checked === true, element: document.activeElement }
            if (checked !== true) setRemainingExpanded(true)
            onToggle(item, checked === true)
          }}
        />
        <span
          data-testid="note-item-content"
          className={cn('min-w-0 whitespace-pre-wrap break-words [overflow-wrap:anywhere]', item.is_completed && 'text-muted-foreground line-through')}
        >
          {item.content}
        </span>
      </label>
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
