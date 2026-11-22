/** Human input controls read timers. Polls and cache writes never renew this window. */
import { useSyncExternalStore } from 'react'
import type { QueryClient } from '@tanstack/react-query'

export const HUMAN_IDLE_MS = 5 * 60_000
let lastInput = Date.now()
const listeners = new Set<() => void>()
export function humanRemainingSeconds() { return Math.max(0, Math.min(300, Math.ceil((HUMAN_IDLE_MS - (Date.now() - lastInput)) / 1000))) }
export function humanActive() {
  return (typeof document === 'undefined' || document.visibilityState === 'visible') && Date.now() - lastInput < HUMAN_IDLE_MS
}
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener) } }
export function useHumanActive() { return useSyncExternalStore(subscribe, humanActive, () => false) }
export function startHumanActivity(client: QueryClient) {
  let timer: ReturnType<typeof setTimeout>
  let interrupted = document.visibilityState !== 'visible'
  const notify = () => { for (const listener of listeners) listener() }
  const input = () => {
    if (document.visibilityState !== 'visible') { interrupted = true; notify(); return }
    const returning = interrupted || !humanActive()
    interrupted = false
    lastInput = Date.now()
    clearTimeout(timer)
    timer = setTimeout(notify, HUMAN_IDLE_MS)
    if (returning) {
      // Every open read view revalidates its authenticated API. Never manufacture
      // fresh data or change outbox/reminder/Mimi execution lifecycles here.
      void client.invalidateQueries({ type: 'active', predicate: query => query.options.queryFn !== undefined })
    }
    notify()
  }
  const events = ['pointerdown', 'keydown', 'focus', 'visibilitychange'] as const
  for (const name of events) window.addEventListener(name, input, true)
  input()
  return () => {
    clearTimeout(timer)
    for (const name of events) window.removeEventListener(name, input, true)
  }
}
