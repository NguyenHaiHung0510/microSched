import { useLayoutEffect, useRef } from 'react'
import { Textarea } from '@/components/ui/textarea'
import { singleLineTitle } from '@/task-title'

export function TaskTitleInput({ id, value, disabled, onChange }: {
  id: string
  value: string
  disabled: boolean
  onChange: (value: string) => void
}) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const composing = useRef(false)
  useLayoutEffect(() => {
    const input = ref.current
    if (!input) return
    const resize = () => {
      // scrollHeight also works where field-sizing: content is unavailable.
      input.style.height = 'auto'
      input.style.height = `${input.scrollHeight + input.offsetHeight - input.clientHeight}px`
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(input)
    return () => observer.disconnect()
  }, [value])
  return <Textarea
    id={id}
    ref={ref}
    data-testid="task-title-input"
    rows={1}
    className="min-h-11 resize-none overflow-hidden bg-card [overflow-wrap:anywhere]"
    value={singleLineTitle(value)}
    required
    minLength={1}
    disabled={disabled}
    onCompositionStart={() => { composing.current = true }}
    onCompositionEnd={() => { composing.current = false }}
    onChange={event => {
      const input = event.currentTarget
      const next = singleLineTitle(input.value)
      const caret = singleLineTitle(input.value.slice(0, input.selectionStart)).length
      onChange(next)
      if (next !== input.value) requestAnimationFrame(() => {
        if (input.isConnected && document.activeElement === input) input.setSelectionRange(caret, caret)
      })
    }}
    onKeyDown={event => {
      if (event.key !== 'Enter') return
      if (composing.current || event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return
      event.preventDefault()
      const form = event.currentTarget.form
      const submitter = form?.querySelector<HTMLButtonElement>('button[type="submit"]')
      // Implicit Enter in the old Input did not bypass a disabled submit button.
      if (!event.repeat && !disabled && submitter && !submitter.disabled) form?.requestSubmit(submitter)
    }}
  />
}
