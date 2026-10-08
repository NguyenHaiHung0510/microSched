import { useCallback, useSyncExternalStore } from 'react'

// This Vite entry mounts with createRoot; no server hydration is supported.
export function usePreviewExpired(expiresAt: string): boolean {
  const deadline = Date.parse(expiresAt)
  const getSnapshot = useCallback(() => !Number.isFinite(deadline) || Date.now() >= deadline, [deadline])
  const subscribe = useCallback((notify: () => void) => {
    // One finite deadline timer per mounted preview. Focus/visibility also
    // reconcile elapsed wall time after sleep; no interval or network polling.
    const delay = deadline - Date.now()
    const timer = Number.isFinite(delay) && delay > 0
      ? window.setTimeout(notify, Math.min(delay, 2_147_483_647))
      : null
    window.addEventListener('focus', notify)
    document.addEventListener('visibilitychange', notify)
    return () => {
      if (timer !== null) window.clearTimeout(timer)
      window.removeEventListener('focus', notify)
      document.removeEventListener('visibilitychange', notify)
    }
  }, [deadline])
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
}
