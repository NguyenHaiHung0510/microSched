/** One pending activity signal per tab, consumed once by the next visible state read. */
let pending = false

export function markGardenActivity() {
  if (typeof document !== 'undefined' && document.visibilityState === 'visible') pending = true
}

export function gardenPresenceHeaders(): Record<string, string> {
  if (!pending || typeof document === 'undefined' || document.visibilityState !== 'visible') return {}
  pending = false
  return { 'X-MiGarden-Visible': '1' }
}

export function listenGardenActivity() {
  markGardenActivity()
  const events = ['pointerdown', 'keydown', 'focus', 'visibilitychange'] as const
  const options = { capture: true }
  for (const event of events) window.addEventListener(event, markGardenActivity, options)
  return () => {
    for (const event of events) window.removeEventListener(event, markGardenActivity, options)
    pending = false
  }
}
