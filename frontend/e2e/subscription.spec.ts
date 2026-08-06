import { expect } from '@playwright/test'

import { test as trackerTest } from './fixtures/tracker'

/**
 * Mock for the subscription slice (`/api/subscriptions/**`) and the public
 * settings API (`/api/settings/**`). Registered AFTER the tracker fixture so
 * these routes win over the shared api-fallback handler from tasks.ts.
 */
type FixtureSubscription = {
  id: string
  tracker_id: string
  name: string
  amount: number | null
  list_amount: number | null
  period_count: number
  period_unit: 'day' | 'week' | 'month' | 'year'
  started_on: string
  expires_on: string
  auto_renew: boolean
  canceled_at: string | null
  note_md: string | null
  deleted_at: string | null
  created_at: string
  updated_at: string
  status: 'active' | 'canceled' | 'expired'
  days_left: number
  monthly_amount: number | null
  corrupted: boolean
}

function nowIso(): string {
  return new Date().toISOString()
}

function subscription(overrides: Partial<FixtureSubscription>): FixtureSubscription {
  return {
    id: 'sub-001',
    tracker_id: 'tracker-002',
    name: 'Sub AI',
    amount: 260000,
    list_amount: 300000,
    period_count: 1,
    period_unit: 'month',
    started_on: '2026-08-01',
    expires_on: '2026-08-31',
    auto_renew: true,
    canceled_at: null,
    note_md: null,
    deleted_at: null,
    created_at: nowIso(),
    updated_at: nowIso(),
    status: 'active',
    days_left: 25,
    monthly_amount: 260000,
    corrupted: false,
    ...overrides,
  }
}

type SubscriptionApiState = {
  subscriptions: FixtureSubscription[]
  settings: Array<{ key: string; value: number | boolean }>
  renews: number
}

export const test = trackerTest.extend<{ subscriptionApi: SubscriptionApiState }>({
  subscriptionApi: [
    async ({ page }, use) => {
      const state: SubscriptionApiState = {
        subscriptions: [
          subscription({ id: 'sub-001', name: 'Sub AI' }),
          subscription({
            id: 'sub-002',
            name: 'Sub Google IA Platform',
            amount: 300000,
            expires_on: '2026-08-08',
            days_left: 2,
          }),
          subscription({
            id: 'sub-003',
            name: 'Đã huỷ',
            amount: 99000,
            status: 'canceled',
            canceled_at: nowIso(),
            auto_renew: false,
          }),
        ],
        settings: [
          { key: 'subscription_expiry_lead_days', value: 3 },
          { key: 'show_list_price', value: true },
        ],
        renews: 0,
      }

      await page.route('**/api/subscriptions**', async (route) => {
        const request = route.request()
        const method = request.method()
        const path = new URL(request.url()).pathname

        if (path === '/api/subscriptions' && method === 'GET') {
          await route.fulfill(jsonResponse({ items: state.subscriptions }))
          return
        }
        if (path === '/api/subscriptions' && method === 'POST') {
          const payload = JSON.parse(request.postData() ?? '{}') as Partial<FixtureSubscription>
          const created = subscription({
            id: payload.id ?? `sub-${Date.now()}`,
            name: payload.name ?? '',
            tracker_id: payload.tracker_id ?? 'tracker-002',
            amount: payload.amount ?? null,
            period_unit: payload.period_unit ?? 'month',
            started_on: payload.started_on ?? '',
            expires_on: payload.expires_on ?? '',
            auto_renew: payload.auto_renew ?? false,
          })
          state.subscriptions.push(created)
          await route.fulfill(jsonResponse(created, 201))
          return
        }

        const match = path.match(/^\/api\/subscriptions\/([^/]+)(?:\/(renew|cancel|uncancel|restore))?$/)
        if (!match) {
          await route.fulfill({ status: 404 })
          return
        }
        const [, id, action] = match
        const current = state.subscriptions.find((item) => item.id === id)
        if (!current) {
          await route.fulfill({ status: 404 })
          return
        }
        if (action === 'renew') {
          state.renews += 1
          const payload = JSON.parse(request.postData() ?? '{}') as { new_expires_on?: string }
          const updated = {
            ...current,
            updated_at: nowIso(),
            expires_on: payload.new_expires_on ?? current.expires_on,
          }
          state.subscriptions = state.subscriptions.map((item) => (item.id === id ? updated : item))
          await route.fulfill(
            jsonResponse({ subscription: updated, entry_id: 'entry-001', created: true }),
          )
          return
        }
        if (action === 'cancel') {
          const updated = { ...current, status: 'canceled' as const, canceled_at: nowIso() }
          state.subscriptions = state.subscriptions.map((item) => (item.id === id ? updated : item))
          await route.fulfill(jsonResponse(updated))
          return
        }
        if (action === 'uncancel') {
          const updated = { ...current, status: 'active' as const, canceled_at: null }
          state.subscriptions = state.subscriptions.map((item) => (item.id === id ? updated : item))
          await route.fulfill(jsonResponse(updated))
          return
        }
        if (action === 'restore') {
          await route.fulfill(jsonResponse({ id, status: 'restored' }))
          return
        }
        if (method === 'DELETE') {
          state.subscriptions = state.subscriptions.filter((item) => item.id !== id)
          await route.fulfill({ status: 204 })
          return
        }
        await route.fulfill(jsonResponse(current))
      })

      await page.route('**/api/settings**', async (route) => {
        const request = route.request()
        const method = request.method()
        const path = new URL(request.url()).pathname
        if (path === '/api/settings' && method === 'GET') {
          await route.fulfill(jsonResponse({ items: state.settings }))
          return
        }
        const match = path.match(/^\/api\/settings\/([^/]+)$/)
        if (!match) {
          await route.fulfill({ status: 404 })
          return
        }
        const key = match[1]
        if (method === 'PATCH') {
          const payload = JSON.parse(request.postData() ?? '{}') as { value: number | boolean }
          const item = { key, value: payload.value }
          state.settings = [...state.settings.filter((entry) => entry.key !== key), item]
          await route.fulfill(jsonResponse(item))
          return
        }
        const found = state.settings.find((item) => item.key === key)
        await route.fulfill(jsonResponse(found ?? { key, value: null }))
      })

      await use(state)
    },
    { auto: true },
  ],
})

function jsonResponse(body: unknown, status = 200) {
  return {
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  }
}

test('highlight scrolls to the right card without auto-opening a dialog', async ({
  page,
}) => {
  await page.goto('/subscription?highlight=sub-002')
  await expect(page.getByTestId('subscription-screen')).toBeVisible()
  await expect(
    page.locator('[data-testid="subscription-card"][data-subscription-id="sub-002"]'),
  ).toHaveAttribute('data-highlighted', 'true')
  await expect(page.getByTestId('subscription-renew-form')).toHaveCount(0)
  await expect(page.getByTestId('subscription-dialog')).toHaveCount(0)
})

test('cold-load /subscription and back returns to the tab block', async ({ page }) => {
  await page.goto('/subscription')
  await expect(page.getByTestId('subscription-screen')).toBeVisible()
  await page.getByRole('button', { name: 'Quay lại' }).click()
  await expect(page.getByRole('tablist')).toBeVisible()
  await expect(page).toHaveURL('/')
})

test('renew form previews the amount and new expiry before confirm', async ({ page }) => {
  await page.goto('/subscription')
  await expect(page.getByTestId('subscription-screen')).toBeVisible()
  await page
    .locator('[data-testid="subscription-renew"][data-subscription-id="sub-001"]')
    .click()
  const form = page.getByTestId('subscription-renew-form')
  await expect(form).toBeVisible()
  await expect(page.getByTestId('subscription-renew-summary')).toContainText('260.000 ₫')
  await expect(page.getByTestId('subscription-renew-summary')).toContainText('hết hạn mới')

  await form.getByLabel('Số tiền').fill('300000')
  await expect(page.getByTestId('subscription-renew-summary')).toContainText('300.000 ₫')
})

export type { FixtureSubscription }
