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

function daysAgoIso(days: number): string {
  return new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10)
}

/** Today's calendar date in Vietnam, mirroring the app's ``todayVn()``. */
function todayVnIso(): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Ho_Chi_Minh',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
}

/** Mirror of ``addPeriod`` (§4.2) so the mock can apply the server veto. */
function addPeriodFixture(
  day: string,
  count: number,
  unit: FixtureSubscription['period_unit'],
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

function formatDmy(iso: string): string {
  const [year, month, day] = iso.split('-')
  return `${day}/${month}/${year}`
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
  renewPayloads: Array<Record<string, unknown>>
}

export const test = trackerTest.extend<{ subscriptionApi: SubscriptionApiState }>({
  subscriptionApi: [
    async ({ page }, use) => {
      const state: SubscriptionApiState = {
        subscriptions: [
          subscription({
            id: 'sub-002',
            name: 'Sub Google IA Platform',
            amount: 300000,
            expires_on: '2026-08-08',
            days_left: 2,
          }),
          subscription({ id: 'sub-001', name: 'Sub AI' }),
          // Filler list (F9): enough cards that the highlighted one is far
          // below the fold on both projects, so the e2e can prove a REAL
          // scroll happened instead of a no-op highlight.
          subscription({
            id: 'sub-004',
            name: 'Sub filler 004',
            amount: 49000,
            expires_on: '2026-10-01',
            days_left: 56,
          }),
          subscription({
            id: 'sub-005',
            name: 'Sub filler 005',
            amount: 59000,
            expires_on: '2026-10-02',
            days_left: 57,
          }),
          subscription({
            id: 'sub-006',
            name: 'Sub filler 006',
            amount: 69000,
            expires_on: '2026-10-03',
            days_left: 58,
          }),
          subscription({
            id: 'sub-007',
            name: 'Sub filler 007',
            amount: 79000,
            expires_on: '2026-10-04',
            days_left: 59,
          }),
          subscription({
            id: 'sub-008',
            name: 'Sub filler 008',
            amount: 89000,
            expires_on: '2026-10-05',
            days_left: 60,
          }),
          subscription({
            id: 'sub-009',
            name: 'Sub filler 009',
            amount: 99000,
            expires_on: '2026-10-06',
            days_left: 61,
          }),
          subscription({
            id: 'sub-010',
            name: 'Sub filler 010',
            amount: 109000,
            expires_on: '2026-10-07',
            days_left: 62,
          }),
          subscription({
            id: 'sub-011',
            name: 'Sub filler 011',
            amount: 129000,
            expires_on: '2026-10-08',
            days_left: 63,
          }),
          subscription({
            id: 'sub-012',
            name: 'Sub filler 012',
            amount: 199000,
            expires_on: '2026-10-09',
            days_left: 64,
          }),
          subscription({
            id: 'sub-003',
            name: 'Đã huỷ',
            amount: 99000,
            status: 'canceled',
            canceled_at: nowIso(),
            auto_renew: false,
          }),
          subscription({
            id: 'sub-lapsed',
            name: 'Sub hết hạn từ lâu',
            amount: 120000,
            started_on: daysAgoIso(150),
            expires_on: daysAgoIso(90),
            status: 'expired',
            auto_renew: false,
            days_left: -90,
          }),
        ],
        settings: [
          { key: 'subscription_expiry_lead_days', value: 3 },
          { key: 'show_list_price', value: true },
        ],
        renews: 0,
        renewPayloads: [],
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
          const payload = JSON.parse(request.postData() ?? '{}') as {
            new_expires_on?: string
          }
          state.renewPayloads.push(payload)
          // Mirror the server veto (§4.2): when the client omits the date, the
          // new expiry is anchored to max(expires_on, today) + one period.
          const vetoAnchor =
            current.expires_on > todayVnIso() ? current.expires_on : todayVnIso()
          const updated = {
            ...current,
            updated_at: nowIso(),
            expires_on:
              payload.new_expires_on ??
              addPeriodFixture(
                vetoAnchor,
                current.period_count,
                current.period_unit,
                Number(current.started_on.slice(8, 10)),
              ),
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

test('mobile auto-renew and list-price controls expose 44px hit areas', async ({ page }) => {
  await page.goto('/subscription')
  await expect(page.getByTestId('subscription-screen')).toBeVisible()
  await page.getByRole('button', { name: 'Đăng ký mới' }).click()

  const autoRenew = page.getByTestId('subscription-auto-renew-hit-area')
  const listPrice = page.getByTestId('settings-list-price-hit-area')
  await expect(autoRenew).toBeVisible()
  await expect(listPrice).toBeVisible()

  for (const [name, locator] of [
    ['auto-renew', autoRenew],
    ['list-price', listPrice],
  ] as const) {
    const box = await locator.boundingBox()
    expect(box, `${name} hit area must be visible`).not.toBeNull()
    expect(box!.height, `${name} hit area must be at least 44px`).toBeGreaterThanOrEqual(44)
  }
})

test('lapsed subscription renews from today, not its stale expiry (F1)', async ({
  page,
  subscriptionApi,
}) => {
  const lapsed = subscriptionApi.subscriptions.find((item) => item.id === 'sub-lapsed')
  expect(lapsed).toBeDefined()
  const anchor =
    lapsed!.expires_on > todayVnIso() ? lapsed!.expires_on : todayVnIso()
  const expected = addPeriodFixture(
    anchor,
    lapsed!.period_count,
    lapsed!.period_unit,
    Number(lapsed!.started_on.slice(8, 10)),
  )

  await page.goto('/subscription')
  await expect(page.getByTestId('subscription-screen')).toBeVisible()
  await page
    .locator('[data-testid="subscription-renew"][data-subscription-id="sub-lapsed"]')
    .click()
  const form = page.getByTestId('subscription-renew-form')
  await expect(form).toBeVisible()
  // The preview must show a FUTURE expiry anchored to today — not a date
  // computed from the stale March milestone.
  await expect(page.getByTestId('subscription-renew-summary')).toContainText(
    formatDmy(expected),
  )
  await form.getByRole('button', { name: 'Ghi gia hạn' }).click()
  await expect(page.getByTestId('subscription-renew-dialog')).toHaveCount(0)

  // The untouched default date is NOT sent: the server keeps the veto
  // max(expires_on, today), so a client clock race cannot land a stale expiry.
  const sent = subscriptionApi.renewPayloads.at(-1)
  expect(sent).toBeDefined()
  expect(sent!['new_expires_on']).toBeUndefined()
  const updated = subscriptionApi.subscriptions.find((item) => item.id === 'sub-lapsed')
  expect(updated!.expires_on).toBe(expected)
})

test('hostile highlight value cannot crash or highlight anything (F5)', async ({
  page,
}) => {
  // Unbalanced quote + attribute-injection text: with the old
  // ``querySelector(`[data-subscription-id="${highlightId}"]`)`` this throws a
  // SyntaxError in the effect and unmounts the screen.
  const hostile = encodeURIComponent('sub-002" onerror="alert(1)')
  await page.goto(`/subscription?highlight=${hostile}`)
  await expect(page.getByTestId('subscription-screen')).toBeVisible()
  await expect(page.locator('[data-highlighted="true"]')).toHaveCount(0)
  await expect(page.getByTestId('subscription-renew-form')).toHaveCount(0)
})

test('back from an in-app subscription entry does not loop (F6)', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('tab', { name: 'Theo dõi' }).click()
  await page.getByTestId('subscription-entry').click()
  await expect(page.getByTestId('subscription-screen')).toBeVisible()
  await page.getByRole('button', { name: 'Quay lại' }).click()
  await expect(page).toHaveURL('/')
  await expect(page.getByTestId('subscription-screen')).toHaveCount(0)
  // The /subscription entry was REPLACED, so browser-Back must not loop back
  // into the screen (it returns to the previous '/' entry instead).
  await page.goBack()
  await expect(page).toHaveURL('/')
  await expect(page.getByTestId('subscription-screen')).toHaveCount(0)
})

test('highlight really scrolls the card into the viewport (F9)', async ({ page }) => {
  await page.goto('/subscription?highlight=sub-lapsed')
  await expect(page.getByTestId('subscription-screen')).toBeVisible()
  const card = page.locator(
    '[data-testid="subscription-card"][data-subscription-id="sub-lapsed"]',
  )
  await expect(card).toHaveAttribute('data-highlighted', 'true')
  // scrollIntoView must have moved the page: the card's bounding rect sits
  // inside the viewport AND the window really scrolled. A no-op highlight on a
  // short list keeps scrollY at 0 and the card below the fold.
  await expect(card).toBeInViewport()
  const scrollY = await page.evaluate(() => window.scrollY)
  expect(scrollY).toBeGreaterThan(0)
  const box = await card.boundingBox()
  const viewport = page.viewportSize()
  expect(box).not.toBeNull()
  expect(viewport).not.toBeNull()
  // scrollIntoView is `smooth`: the rect measured right after toBeInViewport
  // can still be a mid-animation frame (taller 44px buttons moved the card
  // further down, so the animation covers more distance). Poll until the
  // FINAL position satisfies the acceptance — a genuinely clamped overflow
  // still fails here, only transient frames are skipped.
  await expect
    .poll(async () => {
      const current = await card.boundingBox()
      return current ? Math.round(current.y + current.height) : Number.NaN
    }, { timeout: 5000 })
    .toBeLessThanOrEqual(viewport!.height + 2)
  const settled = await card.boundingBox()
  // boundingBox() is viewport-relative, so a plain y-range check proves the
  // card sits on screen after the real scroll.
  expect(settled!.y).toBeGreaterThanOrEqual(-2)
  expect(settled!.y + settled!.height).toBeLessThanOrEqual(viewport!.height + 2)
})

export type { FixtureSubscription }
