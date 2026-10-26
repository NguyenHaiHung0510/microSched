import { useCallback, useLayoutEffect, useRef } from 'react'

/** Keep an occurrence at its visual offset in the actual reminder panel scroller. */
export function useHistoryPosition() {
  const rootRef = useRef<HTMLElement>(null)
  const generation = useRef(0)
  const anchor = useRef<{
    container: HTMLElement
    candidates: { id: string; offset: number }[]
    focusFrom: Element | null
    focusAllowed: boolean
    focused: boolean
    generation: number
    settled: boolean
  } | null>(null)
  const restore = useCallback(() => {
    const saved = anchor.current
    if (!saved || !rootRef.current) return true
    const elements = Array.from(rootRef.current.querySelectorAll<HTMLElement>('[data-occurrence]'))
    for (const candidate of saved.candidates) {
      const row = elements.find(element => element.dataset.occurrence === candidate.id)
      if (!row) continue
      const offset = row.getBoundingClientRect().top - saved.container.getBoundingClientRect().top
      saved.container.scrollTop += offset - candidate.offset
      if (row.getAttribute('aria-busy') === 'true') return false
      const active = document.activeElement
      if (!saved.focused && saved.focusAllowed && (active === document.body || active === saved.focusFrom)) {
        const control = row.querySelector<HTMLButtonElement>('[data-testid="history-handle"]:not(:disabled)')
        ;(control ?? row).focus({ preventScroll: true })
        saved.focused = true
      }
      return true
    }
    if (!saved.focused && saved.focusAllowed && document.activeElement === document.body) {
      rootRef.current.querySelector<HTMLElement>('[data-history-heading]')?.focus({ preventScroll: true })
      saved.focused = true
    }
    return true
  }, [])
  const capturePosition = useCallback((id?: string) => {
    const root = rootRef.current
    const container = root?.closest<HTMLElement>('[data-testid="reminder-center"]')
    if (!root || !container) return
    const top = container.getBoundingClientRect().top
    const rows = Array.from(root.querySelectorAll<HTMLElement>('[data-occurrence]'))
    const requested = rows.find(row => row.dataset.occurrence === id)
    const current = requested && requested.getBoundingClientRect().bottom > top && requested.getBoundingClientRect().top < container.getBoundingClientRect().bottom
      ? requested : rows.find(row => row.getBoundingClientRect().bottom > top)
    if (!current) return
    const index = rows.indexOf(current)
    const active = document.activeElement
    const captured = ++generation.current
    const offset = current.getBoundingClientRect().top - top
    anchor.current = {
      container,
      candidates: [current, ...rows.slice(index + 1), ...rows.slice(0, index).reverse()].map(row => ({ id: row.dataset.occurrence!, offset })),
      focusFrom: active,
      focusAllowed: active === document.body || current.contains(active),
      focused: false,
      generation: captured,
      settled: false,
    }
    return captured
  }, [])
  const forgetPosition = useCallback(() => { anchor.current = null }, [])
  const settlePosition = useCallback((captured?: number) => {
    requestAnimationFrame(() => {
      if (!anchor.current || anchor.current.generation !== captured) return
      anchor.current.settled = true
      if (restore()) anchor.current = null
    })
  }, [restore])
  useLayoutEffect(() => {
    const settled = anchor.current?.settled
    if (restore() && settled) anchor.current = null
  })
  useLayoutEffect(() => () => { anchor.current = null }, [])
  return { rootRef, capturePosition, settlePosition, forgetPosition }
}
