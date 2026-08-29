/// <reference lib="webworker" />

import { createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'

import { type PushNotificationPayload, showPushNotification } from './sw-notification'

declare const self: ServiceWorkerGlobalScope

precacheAndRoute(self.__WB_MANIFEST)

registerRoute(
  new NavigationRoute(createHandlerBoundToURL('index.html'), {
    denylist: [/^\/auth\//, /^\/api\//],
  })
)

self.addEventListener('push', (event: PushEvent) => {
  let data: PushNotificationPayload = {}
  if (event.data) {
    try {
      data = event.data.json() as PushNotificationPayload
    } catch {
      data = {}
    }
  }

  event.waitUntil(showPushNotification(self.registration, data))
})

self.addEventListener('notificationclick', (event: NotificationEvent) => {
  event.notification.close()
  const targetUrl = (event.notification.data?.url as string) ?? '/'

  event.waitUntil(
    self.clients.matchAll({ type: 'window' }).then((clientList) => {
      for (const client of clientList) {
        if ('focus' in client) {
          client.navigate(targetUrl)
          return client.focus()
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl)
      }
    })
  )
})
