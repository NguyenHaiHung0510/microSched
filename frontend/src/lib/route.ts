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

/** Push a new URL and notify subscribers; back-end popstate is also caught. */
export function navigate(path: string): void {
  if (snapshot() === path) return
  window.history.pushState(null, '', path)
  window.dispatchEvent(new PopStateEvent('popstate'))
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
