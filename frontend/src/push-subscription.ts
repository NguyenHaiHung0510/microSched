import { apiRequest } from '@/api'
import type { MimiDeviceProof } from '@/mimi-api'

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
export async function ensurePushSubscription(): Promise<MimiDeviceProof> {
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

  const registration = await boundedPushStep(navigator.serviceWorker.ready)
  const { public_key: publicKey } = await apiRequest<{ public_key: string }>(
    '/api/push/vapid-public-key',
  )
  const subscription = await boundedPushStep(registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(publicKey),
  }))
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
  const registered = await apiRequest<{ id: string }>('/api/push/subscribe', {
    method: 'POST',
    body: JSON.stringify(body),
  })
  const proof = { subscription_id: registered.id, endpoint: body.endpoint, p256dh: body.p256dh, auth: body.auth }
  localStorage.setItem(await subscriptionIdKey(body.endpoint), registered.id)
  return proof
}

async function subscriptionIdKey(endpoint: string) {
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(endpoint))
  return 'mimi-push-registration:' + Array.from(new Uint8Array(hash)).map((b) => b.toString(16).padStart(2, '0')).join('')
}
async function boundedPushStep<T>(work: Promise<T>): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try { return await Promise.race([work, new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('Chưa xác định kết quả đăng ký thiết bị. Không tự đăng ký lại.')), 20_000) })]) } finally { clearTimeout(timer) }
}
// Read only: no requestPermission, subscription creation, or registration POST.
export async function readExistingPushProof(): Promise<MimiDeviceProof | null> {
  if (!('serviceWorker' in navigator)) return null
  const registration = await navigator.serviceWorker.getRegistration()
  if (!registration) return null
  const subscription = await boundedPushStep(registration.pushManager.getSubscription())
  if (!subscription) return null
  const serialized = subscription.toJSON()
  const id = localStorage.getItem(await subscriptionIdKey(subscription.endpoint))
  if (!id || !serialized.keys?.p256dh || !serialized.keys.auth) return null
  return { subscription_id: id, endpoint: subscription.endpoint, p256dh: serialized.keys.p256dh, auth: serialized.keys.auth }
}
