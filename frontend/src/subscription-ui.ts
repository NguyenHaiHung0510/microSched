/** Subscription-slice types, pure rules, and the single mutation seam (011c).
 *
 * Mirrors ``tracker-ui.ts``: pure helpers are unit-testable without the DOM,
 * and every write of the subscription screen goes through the mutations this
 * module returns (the 017 offline-outbox door, same as the tracker seam).
 */

import { useMutation } from '@tanstack/react-query'

import { apiRequest } from '@/api'
import { VIETNAM_TIME_ZONE } from '@/calendar-ui'
import { uuidv7 } from '@/lib/uuidv7'
import { formatVnd, trackerQueryKey, type Tracker } from '@/tracker-ui'

export type SubscriptionStatus = 'active' | 'canceled' | 'expired'
export type PeriodUnit = 'day' | 'week' | 'month' | 'year'

export type Subscription = {
  id: string
  tracker_id: string
  name: string
  amount: number | null
  list_amount: number | null
  period_count: number
  period_unit: PeriodUnit
  started_on: string
  expires_on: string
  auto_renew: boolean
  canceled_at: string | null
  note_md: string | null
  deleted_at: string | null
  created_at: string | null
  updated_at: string | null
  status: SubscriptionStatus
  days_left: number
  monthly_amount: number | null
  corrupted: boolean
}

export type SubscriptionWritePayload = {
  name: string
  tracker_id: string
  amount: number
  list_amount?: number | null
  period_count: number
  period_unit: PeriodUnit
  started_on: string
  expires_on: string
  auto_renew: boolean
  note_md?: string | null
}

export type RenewPayload = {
  entry_id: string
  amount?: number
  occurred_at?: string
  new_expires_on?: string
  note_md?: string
  clear_canceled?: boolean
}

export type RenewResult = {
  subscription: Subscription
  entry_id: string
  created: boolean
}

export type F6Upcoming = {
  subscription_id: string
  name: string
  amount: number | null
  monthly_amount: number | null
  expires_on: string
  days_left: number
  corrupted: boolean
}

export type SettingsItem = { key: string; value: number | boolean }

export const subscriptionInvalidationKey = ['subscription'] as const

export function subscriptionQueryKey(kind: 'subscriptions' | 'settings') {
  return ['subscription', kind] as const
}

/** Mirror of the backend ``add_period`` (011c §4.2) for the renew preview.
 *
 * ``day``/``week`` use plain day arithmetic; ``month``/``year`` clamp to the
 * anchor day (the subscription's ``started_on.day``) so 31/01 → 28/02 → 31/03.
 * The preview must match what the server will store — the user sees the new
 * expiry date BEFORE pressing confirm (§5.3).
 */
export function addPeriod(
  day: string,
  count: number,
  unit: PeriodUnit,
  anchorDay: number,
): string {
  if (unit === 'day' || unit === 'week') {
    const days = count * (unit === 'week' ? 7 : 1)
    const value = new Date(`${day}T00:00:00Z`)
    value.setUTCDate(value.getUTCDate() + days)
    return value.toISOString().slice(0, 10)
  }
  const [year, month] = day.split('-').map(Number)
  const months = count * (unit === 'year' ? 12 : 1)
  const total = (year - 1970) * 12 + (month - 1) + months
  const targetYear = 1970 + Math.floor(total / 12)
  const targetMonth = (total % 12) + 1
  const lastDay = new Date(Date.UTC(targetYear, targetMonth, 0)).getUTCDate()
  const targetDay = Math.min(anchorDay, lastDay)
  return `${targetYear}-${String(targetMonth).padStart(2, '0')}-${String(targetDay).padStart(2, '0')}`
}

/** dd/mm/yyyy rendered in Vietnam time from a plain YYYY-MM-DD calendar date. */
export function formatShortDate(value: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: VIETNAM_TIME_ZONE,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(`${value}T00:00:00Z`))
}

/** Today's calendar date in Vietnam (YYYY-MM-DD), mirroring backend ``_today_vn``.
 *
 * The renew dialog must not anchor a LAPSED subscription's new expiry to its
 * stale milestone (§4.2 veto #8) — the client preview and the server agree on
 * ``max(expires_on, today)`` even across the midnight boundary, because the
 * server re-applies the veto when the client omits ``new_expires_on``.
 */
export function todayVn(): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: VIETNAM_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
}

const periodNames: Record<PeriodUnit, string> = {
  day: 'ngày',
  week: 'tuần',
  month: 'tháng',
  year: 'năm',
}

export function periodLabel(count: number, unit: PeriodUnit): string {
  return `${count} ${periodNames[unit]}`
}

export function amountPerPeriod(amount: number | null, count: number, unit: PeriodUnit): string {
  return amount == null ? 'không đọc được' : `${formatVnd(amount)} / ${periodLabel(count, unit)}`
}

export function statusLabel(status: SubscriptionStatus): string {
  return status === 'active' ? 'Đang hoạt động' : status === 'canceled' ? 'Đã huỷ' : 'Hết hạn'
}

export function daysLeftLabel(daysLeft: number): string {
  if (daysLeft < 0) return `Trễ ${-daysLeft} ngày`
  if (daysLeft === 0) return 'Hết hạn hôm nay'
  return `Còn ${daysLeft} ngày`
}

/** Only finance+money trackers can host a subscription (§2.5). */
export function subscriptionTrackers(trackers: Tracker[]): Tracker[] {
  return trackers.filter((tracker) => tracker.kind === 'finance' && tracker.input_mode === 'money')
}

export function renewSummary(
  name: string,
  amount: number | null,
  newExpiresOn: string,
): string {
  return `Ghi ${amount == null ? '…' : formatVnd(amount)} vào ${name} · hết hạn mới: ${formatShortDate(newExpiresOn)}`
}

/** Seam: every subscription/settings write goes through these mutations. */
export function useSubscriptionWrites(refresh: () => void) {
  const createSubscription = useMutation({
    mutationFn: (payload: SubscriptionWritePayload) =>
      apiRequest<Subscription>('/api/subscriptions', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: refresh,
  })
  const updateSubscription = useMutation({
    mutationFn: ({
      subscriptionId,
      payload,
    }: {
      subscriptionId: string
      payload: Partial<SubscriptionWritePayload>
    }) =>
      apiRequest<Subscription>(`/api/subscriptions/${subscriptionId}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    onSuccess: refresh,
  })
  const cancelSubscription = useMutation({
    mutationFn: (subscriptionId: string) =>
      apiRequest<Subscription>(`/api/subscriptions/${subscriptionId}/cancel`, { method: 'POST' }),
    onSuccess: refresh,
  })
  const uncancelSubscription = useMutation({
    mutationFn: (subscriptionId: string) =>
      apiRequest<Subscription>(`/api/subscriptions/${subscriptionId}/uncancel`, { method: 'POST' }),
    onSuccess: refresh,
  })
  const renew = useMutation({
    mutationFn: ({ subscriptionId, payload }: { subscriptionId: string; payload: RenewPayload }) =>
      apiRequest<RenewResult>(`/api/subscriptions/${subscriptionId}/renew`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: refresh,
  })
  const deleteSubscription = useMutation({
    mutationFn: (subscriptionId: string) =>
      apiRequest<void>(`/api/subscriptions/${subscriptionId}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })
  const restoreSubscription = useMutation({
    mutationFn: (subscriptionId: string) =>
      apiRequest<{ id: string; status: 'restored' }>(
        `/api/subscriptions/${subscriptionId}/restore`,
        { method: 'POST' },
      ),
    onSuccess: refresh,
  })
  const setSetting = useMutation({
    mutationFn: ({ key, value }: { key: string; value: number | boolean }) =>
      apiRequest<SettingsItem>(`/api/settings/${key}`, {
        method: 'PATCH',
        body: JSON.stringify({ value }),
      }),
    onSuccess: refresh,
  })
  return {
    createSubscription,
    updateSubscription,
    cancelSubscription,
    uncancelSubscription,
    renew,
    deleteSubscription,
    restoreSubscription,
    setSetting,
  }
}

/** Settings + dashboard share invalidation when a setting changes. */
export function settingsInvalidationKeys() {
  return [subscriptionQueryKey('settings'), trackerQueryKey('dashboard')]
}

/** Build a fresh renew payload; entry_id is kept by the dialog, not regenerated. */
export function renewPayload(subscription: Subscription): RenewPayload {
  const anchor = subscription.expires_on > todayVn() ? subscription.expires_on : todayVn()
  return {
    entry_id: uuidv7(),
    amount: subscription.amount ?? undefined,
    new_expires_on: addPeriod(
      anchor,
      subscription.period_count,
      subscription.period_unit,
      Number(subscription.started_on.slice(8, 10)),
    ),
  }
}
