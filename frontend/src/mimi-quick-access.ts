// Reserve Alt+A only for an unmodified, non-editing application keystroke.
// Browser/OS interception happens before this listener and is never bypassed.
export function acceptsMimiShortcut(event: KeyboardEvent, doc: Document): boolean {
  if (event.defaultPrevented || !event.altKey || event.ctrlKey || event.metaKey || event.shiftKey
    || event.repeat || event.isComposing || event.keyCode === 229
    || event.getModifierState('AltGraph') || event.code !== 'KeyA') return false
  const target = event.target instanceof Element ? event.target : doc.activeElement
  if (target?.closest('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"],[role="combobox"]')) return false
  // Radix dialogs do not always emit aria-modal. Also respect native dialogs,
  // menus and popovers so the shortcut cannot open a second interaction layer.
  if (doc.querySelector('[role="dialog"][data-state="open"],dialog[open],[aria-modal="true"],[role="menu"][data-state="open"],[data-slot="popover-content"][data-state="open"]')) return false
  return true
}

export function focusMimiSurface(workspace = false) {
  const surface = document.querySelector<HTMLElement>(workspace ? '[data-testid="mimi-workspace-center"]' : '#mimi-side-chat')
  if (!surface) return
  const input = surface.querySelector<HTMLTextAreaElement>('[data-testid="mimi-input"]:not(:disabled)')
  // Runs/archived conversations can legitimately disable the composer.
  if (input) input.focus({ preventScroll: true })
  else { surface.tabIndex = -1; surface.focus({ preventScroll: true }) }
}
