import { useId, useMemo, useRef, useState, type ComponentProps, type KeyboardEvent, type FocusEvent, type Ref } from 'react'
import { Popover as Primitive } from 'radix-ui'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent } from '@/components/ui/popover'
import { TaskTitleInput } from '@/TaskTitleInput'
import { rankTitleSuggestions, titleCandidates } from '@/task-title-suggestions'
import { useTaskTitleSuggestions } from '@/use-task-title-suggestions'
import { cn } from '@/lib/utils'

type Props = Omit<ComponentProps<typeof Input>, 'value' | 'onChange' | 'ref'> & {
  value: string
  onChange: (value: string) => void
  ref?: Ref<HTMLInputElement>
  multiline?: boolean
}

/** A compact editable combobox. Selection edits only this field, never a task. */
export function TaskTitleCombobox({ value, onChange, ref, multiline, className, disabled, readOnly, onKeyDown, onFocus, onBlur, ...props }: Props) {
  const uid = useId()
  const listId = `${uid}-titles`
  const hintId = `${uid}-hint`
  const field = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null)
  const anchor = useRef<HTMLDivElement>(null)
  const content = useRef<HTMLDivElement>(null)
  const composing = useRef(false)
  const touchingList = useRef(false)
  const [focused, setFocused] = useState(false)
  const [dismissed, setDismissed] = useState<string | null>(null)
  const [selection, setSelection] = useState({ value: '', index: 0 })
  const source = useTaskTitleSuggestions(Boolean(disabled || readOnly))
  const candidates = useMemo(() => titleCandidates(source.history), [source.history])
  const suggestions = useMemo(() => rankTitleSuggestions(value, candidates), [value, candidates])
  const open = focused && !disabled && !readOnly && dismissed !== value && suggestions.length > 0
  const active = selection.value === value ? Math.min(selection.index, suggestions.length - 1) : 0
  const activeOption = open ? suggestions[active] : undefined

  function change(value: string) {
    onChange(value)
    setDismissed(null)
    source.activate()
  }
  function choose(index: number) {
    const suggestion = suggestions[index]
    if (!suggestion || disabled || readOnly) return
    onChange(suggestion.title)
    setDismissed(suggestion.title)
    field.current?.focus({ preventScroll: true })
  }
  function keyDown(event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) {
    if (composing.current || event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) {
      // A native input's implicit form submit must not accept an IME candidate.
      if (!multiline && event.key === 'Enter') event.preventDefault()
      return
    }
    if (event.key === 'Enter' && event.repeat) {
      event.preventDefault()
      return
    }
    if (event.key === 'Escape' && open) {
      event.preventDefault()
      event.stopPropagation()
      setDismissed(value)
    } else if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && suggestions.length && !disabled && !readOnly) {
      event.preventDefault()
      setDismissed(null)
      const start = open ? active : event.key === 'ArrowDown' ? -1 : 0
      const next = (start + (event.key === 'ArrowDown' ? 1 : -1) + suggestions.length) % suggestions.length
      setSelection({ value, index: next })
      content.current?.querySelector(`#${CSS.escape(`${uid}-option-${next}`)}`)?.scrollIntoView({ block: 'nearest' })
    } else if ((event.key === 'Tab' && !event.shiftKey || event.key === 'Enter') && activeOption &&
      !event.ctrlKey && !event.altKey && !event.metaKey) {
      event.preventDefault()
      if (!event.repeat) choose(active)
    }
    if (!event.defaultPrevented && !multiline) onKeyDown?.(event as KeyboardEvent<HTMLInputElement>)
  }
  const common = {
    role: 'combobox' as const,
    'aria-autocomplete': 'list' as const,
    'aria-expanded': open,
    'aria-controls': open ? listId : undefined,
    'aria-activedescendant': activeOption ? `${uid}-option-${active}` : undefined,
    'aria-describedby': open ? [props['aria-describedby'], hintId].filter(Boolean).join(' ') : props['aria-describedby'],
    autoComplete: 'off',
    onFocus: () => {
      setFocused(true)
      source.activate()
      // The mobile navigation can otherwise obscure an Agenda field near the end.
      if (window.matchMedia('(max-width: 639px)').matches)
        requestAnimationFrame(() => field.current?.scrollIntoView({ block: 'nearest', inline: 'nearest' }))
    },
    onBlur: (event: FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      if (touchingList.current || content.current?.contains(event.relatedTarget as Node | null)) return
      setFocused(false)
    },
    onKeyDown: keyDown,
    onCompositionStart: () => { composing.current = true },
    onCompositionEnd: () => { composing.current = false },
  }

  return <Popover open={open} onOpenChange={next => { if (!next) setDismissed(value) }}>
    <Primitive.Anchor asChild>
      <div ref={anchor} className="min-w-0 flex-1">
        {multiline ? <TaskTitleInput id={props.id ?? uid} value={value} disabled={Boolean(disabled)} onChange={change}
          fieldRef={element => { field.current = element }} suggestionProps={common} /> :
          <Input {...props} {...common} ref={element => {
            field.current = element
            if (typeof ref === 'function') ref(element)
            else if (ref) ref.current = element
          }} value={value} disabled={disabled} readOnly={readOnly} className={cn('scroll-mb-24', className)}
            onFocus={event => { common.onFocus(); onFocus?.(event) }}
            onBlur={event => { common.onBlur(event); onBlur?.(event) }}
            onChange={event => change(event.target.value)} />}
      </div>
    </Primitive.Anchor>
    {open ? <PopoverContent ref={content} sideOffset={4} align="start"
      className="z-50 w-[var(--radix-popover-trigger-width)] max-w-[calc(100vw-24px)] max-h-[min(320px,var(--radix-popover-content-available-height))] rounded-lg p-0 shadow-lg"
      onOpenAutoFocus={event => event.preventDefault()}
      onCloseAutoFocus={event => event.preventDefault()}
      onInteractOutside={event => { if (anchor.current?.contains(event.target as Node)) event.preventDefault() }}
      onPointerDownCapture={() => { touchingList.current = true }}
      onPointerUpCapture={() => { touchingList.current = false }}
      onPointerCancel={() => { touchingList.current = false }}>
      <div id={listId} role="listbox" aria-label="Gợi ý tiêu đề task" className="p-1">
        {suggestions.map((suggestion, index) => <Button key={`${suggestion.kind}:${suggestion.title}`}
          id={`${uid}-option-${index}`} role="option" aria-selected={index === active} tabIndex={-1} type="button"
          variant="ghost" className={cn('h-auto min-h-11 w-full justify-start whitespace-normal rounded-md px-3 py-2 text-left text-base font-normal [overflow-wrap:anywhere] sm:min-h-9 sm:text-sm', index === active && 'bg-accent text-accent-foreground')}
          onMouseDown={event => event.preventDefault()}
          onPointerMove={event => { if (event.pointerType === 'mouse') setSelection({ value, index }) }}
          onClick={() => choose(index)}>{suggestion.title}</Button>)}
      </div>
      <p id={hintId} className="border-t px-3 py-2 text-xs font-normal text-muted-foreground">Tab / Enter để điền · chưa lưu task</p>
    </PopoverContent> : null}
  </Popover>
}
