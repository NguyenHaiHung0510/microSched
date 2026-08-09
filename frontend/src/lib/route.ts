/** Minimal routing seam (011c §5.1): pathname + search, no react-router.
 *
 * The app has exactly two deep links — ``/subscription?highlight=id`` (011c)
 * and ``/reminder-confirm?dispatch=…`` (011b) — so a one-file seam beats a new
 * runtime dependency. The snapshot MUST include ``search``: going from
 * ``/subscription`` to ``/subscription?highlight=id`` is a state change even
 * though the pathname is identical, and ``useSyncExternalStore`` only re-renders
 * when the snapshot value changes.
 */

import { useSyncExternalStore } from 'react'

function subscribe(callback: () => void): () => void {
  window.addEventListener('popstate', callback)
  return () => window.removeEventListener('popstate', callback)
}

function snapshot(): string {
  return `${window.location.pathname}${window.location.search}`
}

const NAV_STATE = { microschedNav: true }

/** Navigate and notify subscribers; popstate (browser Back/Forward) is caught too.
 *
 * ``replace`` swaps the CURRENT entry instead of pushing a new one — used by
 * the subscription back button so browser-Back cannot loop back into
 * ``/subscription`` (F6). Every app navigation stamps ``NAV_STATE`` on the
 * entry so ``hasAppHistory()`` can tell an in-app push from a cold load.
 */
export function navigate(path: string, options: { replace?: boolean } = {}): void {
  if (snapshot() === path) return
  if (options.replace) {
    window.history.replaceState(NAV_STATE, '', path)
  } else {
    window.history.pushState(NAV_STATE, '', path)
  }
  window.dispatchEvent(new PopStateEvent('popstate'))
}

/** True when the current history entry was created by an in-app navigation.
 *
 * A cold-loaded ``/subscription`` has ``history.state === null``; only an
 * app ``navigate()`` stamps the marker. The subscription back button uses this
 * to choose replaceState (no Back-loop) over the spec's plain ``navigate('/')``
 * (cold load, where replacing the initial entry would eat the user's history).
 */
export function hasAppHistory(): boolean {
  return window.history.state?.microschedNav === true
}

/** Current ``pathname + search`` as one string (e.g. ``/subscription?highlight=id``). */
export function useLocation(): string {
  return useSyncExternalStore(subscribe, snapshot, () => '/')
}

/** Parse the query part of a ``useLocation()`` value. */
export function queryParams(location: string): URLSearchParams {
  const search = location.includes('?') ? location.slice(location.indexOf('?')) : ''
  return new URLSearchParams(search)
}
