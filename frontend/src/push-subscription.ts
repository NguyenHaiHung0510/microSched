import { apiRequest } from '@/api'

type PushSubscriptionBody = {
  endpoint: string
  p256dh: string
  auth: string
  user_agent: string
}

function isIOS(): boolean {
  return (
    /iP(hone|ad|od)/.test(navigator.platform) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
  )
}

/** Convert the VAPID base64url value to the BufferSource PushManager requires. */
export function urlBase64ToUint8Array(value: string): Uint8Array<ArrayBuffer> {
  const padded = `${value}${'='.repeat((4 - (value.length % 4)) % 4)}`
  const base64 = padded.replace(/-/g, '+').replace(/_/g, '/')
  const decoded = window.atob(base64)
  const bytes = new Uint8Array(decoded.length)
  for (let index = 0; index < decoded.length; index += 1) {
    bytes[index] = decoded.charCodeAt(index)
  }
  return bytes
}

/**
 * Register the current device before saving any enabled tracker reminder.
 * This ordering avoids the silent "has a time but no push device" state when
 * an existing reminder is edited from a newly used device.
 */
export async function ensurePushSubscription(): Promise<void> {
  if (!('Notification' in window) || !('serviceWorker' in navigator)) {
    throw new Error('Trình duyệt này không hỗ trợ thông báo đẩy.')
  }

  if (isIOS() && !window.matchMedia('(display-mode: standalone)').matches) {
    throw new Error(
      'Cài microSched vào Màn hình chính trước khi bật nhắc — Safari không cho web thường gửi thông báo.',
    )
  }

  const permission = await Notification.requestPermission()
  if (permission !== 'granted') {
    throw new Error('Hãy mở quyền Thông báo cho microSched trong Cài đặt rồi thử lại.')
  }

  const registration = await navigator.serviceWorker.ready
  const { public_key: publicKey } = await apiRequest<{ public_key: string }>(
    '/api/push/vapid-public-key',
  )
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(publicKey),
  })
  const serialized = subscription.toJSON()
  const keys = serialized.keys
  if (!subscription.endpoint || !keys?.p256dh || !keys.auth) {
    throw new Error('Trình duyệt trả về đăng ký thông báo không hợp lệ.')
  }

  const body: PushSubscriptionBody = {
    endpoint: subscription.endpoint,
    p256dh: keys.p256dh,
    auth: keys.auth,
    user_agent: navigator.userAgent,
  }
  await apiRequest('/api/push/subscribe', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
