export type PushNotificationPayload = {
  title?: string
  body?: string
  url?: string
  tag?: string
}

type NotificationRegistration = Pick<ServiceWorkerRegistration, 'showNotification'>

export async function showPushNotification(
  registration: NotificationRegistration,
  data: PushNotificationPayload,
) {
  const title = data.title ?? 'microSched'
  const body = data.body ?? 'Bạn có một lời nhắc.'
  const url = data.url ?? '/'

  await registration.showNotification(title, {
    body,
    icon: '/microsched.svg',
    tag: data.tag,
    data: { url },
  })
}

/** A notification opens a known same-origin read surface; it cannot name a write API. */
export function safeNotificationTarget(value: unknown, origin: string): string | null {
  if (typeof value !== 'string' || !value || value.startsWith('//') || value.includes('\\') || [...value].some((char) => char.charCodeAt(0) <= 32 || char.charCodeAt(0) === 127)) return null
  try {
    const url = new URL(value, origin)
    if (url.origin !== origin || url.username || url.password || url.hash) return null
    const known = ['/', '/mimi', '/reminder-confirm', '/subscription', '/trackers']
    if (!known.includes(url.pathname)) return null
    if (url.pathname === '/mimi') {
      const locator = url.searchParams.get('attention')
      if (!locator || !/^[A-Za-z0-9_-]{1,100}$/.test(locator) || [...url.searchParams.keys()].some((key) => key !== 'attention') || url.searchParams.getAll('attention').length !== 1) return null
    }
    return url.pathname + url.search
  } catch { return null }
}
export async function openNotificationTarget(clients: NotificationClients, value: unknown, origin: string) {
  const target = safeNotificationTarget(value, origin)
  if (!target) return
  const windows = await clients.matchAll({ type: 'window', includeUncontrolled: true })
  const existing = windows.find((client) => { try { return new URL(client.url).origin === origin } catch { return false } })
  if (existing) { await existing.navigate(target); await existing.focus(); return }
  await clients.openWindow(target)
}

type NotificationClients = {
  matchAll(options: { type: 'window'; includeUncontrolled: boolean }): Promise<ReadonlyArray<{ url: string; navigate: (url: string) => Promise<unknown>; focus: () => Promise<unknown> }>>
  openWindow(url: string): Promise<unknown>
}
