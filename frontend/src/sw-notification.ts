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
