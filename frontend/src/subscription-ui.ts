/** Subscription-slice types, pure rules, and the single mutation seam (011c).
 *
 * Mirrors ``tracker-ui.ts``: pure helpers are unit-testable without the DOM,
 * and every write of the subscription screen goes through the mutations this
 * module returns (the 017 offline-outbox door, same as the tracker seam).
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'

import { restoreCancelledDomainTree } from '@/lib/outbox-adapters'
import type { Json } from '@/lib/outbox-db'
import { queuedRequest, type QueuedDeleteReceipt } from '@/lib/queued-mutation'
import { VIETNAM_TIME_ZONE } from '@/calendar-ui'
import { formatVnd, type Tracker } from '@/tracker-ui'

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
export function useSubscriptionWrites() {
  const queryClient = useQueryClient()
  const createSubscription = useMutation({
    mutationFn: ({ payload, requiresPrivate }: { payload: SubscriptionWritePayload & { id: string }; requiresPrivate: boolean }) =>
      queuedRequest<Subscription>(queryClient, 'subscription.create', { path: '/api/subscriptions', body: payload, entityId: payload.id, parentId: payload.tracker_id, requiresPrivate }),
  })
  const updateSubscription = useMutation({
    mutationFn: ({
      subscriptionId,
      requiresPrivate,
      payload,
    }: {
      subscriptionId: string
      requiresPrivate: boolean
      payload: Partial<SubscriptionWritePayload>
    }) => queuedRequest<Subscription>(queryClient, 'subscription.update', { path: `/api/subscriptions/${subscriptionId}`, body: payload, entityId: subscriptionId, requiresPrivate }),
  })
  const cancelSubscription = useMutation({
    mutationFn: ({ subscriptionId, requiresPrivate }: { subscriptionId: string; requiresPrivate: boolean }) => queuedRequest<Subscription>(queryClient, 'subscription.cancel', { path: `/api/subscriptions/${subscriptionId}/cancel`, entityId: subscriptionId, requiresPrivate }),
  })
  const uncancelSubscription = useMutation({
    mutationFn: ({ subscriptionId, requiresPrivate }: { subscriptionId: string; requiresPrivate: boolean }) => queuedRequest<Subscription>(queryClient, 'subscription.uncancel', { path: `/api/subscriptions/${subscriptionId}/uncancel`, entityId: subscriptionId, requiresPrivate }),
  })
  const renew = useMutation({
    mutationFn: ({ subscriptionId, payload, requiresPrivate }: { subscriptionId: string; payload: RenewPayload; requiresPrivate: boolean }) =>
      queuedRequest<RenewResult | null>(queryClient, 'subscription.renew', { path: `/api/subscriptions/${subscriptionId}/renew`, body: payload, entityId: subscriptionId, parentId: subscriptionId, requiresPrivate }),
  })
  const deleteSubscription = useMutation({
    mutationFn: ({ subscription, requiresPrivate }: { subscription: Subscription; requiresPrivate: boolean }) => queuedRequest<QueuedDeleteReceipt | null>(queryClient, 'subscription.delete', { path: `/api/subscriptions/${subscription.id}`, entityId: subscription.id, requiresPrivate, optimisticEntity: JSON.parse(JSON.stringify(subscription)) as Json }),
  })
  const restoreSubscription = useMutation({
    mutationFn: async ({ subscription, requiresPrivate, receipt }: { subscription: Subscription; requiresPrivate: boolean; receipt: QueuedDeleteReceipt | null }): Promise<unknown> => {
      if (receipt?.cancelledRows.length) return restoreCancelledDomainTree(queryClient, receipt.cancelledRows)
      return queuedRequest<{ id: string; status: 'restored' }>(queryClient, 'subscription.restore', {
        path: `/api/subscriptions/${subscription.id}/restore`, entityId: subscription.id, requiresPrivate,
        optimisticEntity: JSON.parse(JSON.stringify(subscription)) as Json,
      })
    },
  })
  const setSetting = useMutation({
    mutationFn: ({ key, value }: { key: 'show_list_price' | 'subscription_expiry_lead_days'; value: number | boolean }) =>
      queuedRequest<SettingsItem>(queryClient, key === 'show_list_price' ? 'setting.show_list_price.update' : 'setting.subscription_expiry_lead_days.update', { path: `/api/settings/${key}`, body: { value }, entityId: key }),
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
