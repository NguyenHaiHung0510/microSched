import { describe, expect, it, vi } from 'vitest'

import { showPushNotification } from './sw-notification'

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
