import { describe, expect, it, vi } from 'vitest'

import { showPushNotification, safeNotificationTarget, openNotificationTarget } from './sw-notification'

describe('service-worker notification delivery', () => {
  it('passes the opaque batch tag to showNotification', async () => {
    const showNotification = vi.fn().mockResolvedValue(undefined)
    const opaqueTag = 'msb-5b4fd43a367fe3f13fcedc1a'

    await showPushNotification(
      { showNotification } as Pick<ServiceWorkerRegistration, 'showNotification'>,
      {
        title: "Hi, it's microSched 🌸",
        body: 'Bạn có 2 thông báo từ app',
        url: '/trackers',
        tag: opaqueTag,
      },
    )

    expect(showNotification).toHaveBeenCalledOnce()
    expect(showNotification).toHaveBeenCalledWith(
      "Hi, it's microSched 🌸",
      expect.objectContaining({ tag: opaqueTag, data: { url: '/trackers' } }),
    )
  })
})

describe('notification click read-only route boundary', () => {
  it.each(['https://other.example/mimi?attention=opaque', '//other.example/', '/api/mimi/receipts/x/undo-preview', '/mimi?attention=x&confirm=true', '/mimi?attention=x&attention=y', '/unknown', '/%6dimi?attention=x', '/mimi?attention=bad%20value', 'javascript:alert(1)'])('rejects unsafe target %s without navigation', async (target) => {
    const clients = { matchAll: vi.fn(), openWindow: vi.fn() }
    expect(safeNotificationTarget(target, 'https://app.example')).toBeNull()
    await openNotificationTarget(clients, target, 'https://app.example')
    expect(clients.matchAll).not.toHaveBeenCalled(); expect(clients.openWindow).not.toHaveBeenCalled()
  })
  it('opens the exact opaque same-origin locator with no confirmation or provider request', async () => {
    const navigate = vi.fn().mockResolvedValue(undefined); const focus = vi.fn().mockResolvedValue(undefined)
    const clients = { matchAll: vi.fn().mockResolvedValue([{ url: 'https://app.example/', navigate, focus }]), openWindow: vi.fn() }
    await openNotificationTarget(clients, '/mimi?attention=opaque_123', 'https://app.example')
    expect(navigate).toHaveBeenCalledWith('/mimi?attention=opaque_123'); expect(focus).toHaveBeenCalledOnce(); expect(clients.openWindow).not.toHaveBeenCalled()
    expect(safeNotificationTarget('/reminder-confirm?dispatch=synthetic', 'https://app.example')).toBe('/reminder-confirm?dispatch=synthetic')
  })
})
