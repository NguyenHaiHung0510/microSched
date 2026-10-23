/// <reference lib="webworker" />

import { createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'

import { type PushNotificationPayload, showPushNotification, openNotificationTarget } from './sw-notification'

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
  event.waitUntil(openNotificationTarget(self.clients, event.notification.data?.url ?? '/', self.location.origin))
})

// Activation is requested only by the visible, draft-safe update control.
self.addEventListener('message', event => {
  if (event.data?.type === 'SKIP_WAITING') void self.skipWaiting()
})
self.addEventListener('activate', event => { event.waitUntil(self.clients.claim()) })
