import { type Page } from '@playwright/test'

import { expect, test } from './fixtures/tracker'

const STANDARD_PROBE_MS = 16_500
const FAST_POLL_GUARD_MS = 2_500
const NO_POLL_PROBE_MS = 3_000

const trackerPaths = [
  '/api/tracker/groups',
  '/api/tracker/trackers',
  '/api/tracker/dashboard',
  '/api/tracker/entries',
  '/api/subscriptions',
  '/api/settings',
] as const

async function openTrackerScreen(page: Page) {
  await page.goto('/')
  await page.getByRole('tab', { name: 'Theo dõi' }).click()
  await expect(page.getByTestId('tracker-grid')).toBeVisible()
}

async function setVisibility(page: Page, state: 'hidden' | 'visible') {
  await page.evaluate((nextState) => {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => nextState,
    })
    Object.defineProperty(document, 'hidden', {
      configurable: true,
      get: () => nextState === 'hidden',
    })
    // TanStack Query v5.101.2 registers its visibilitychange listener on
    // window, so dispatch on that exact event target for the focus wave.
    window.dispatchEvent(new Event('visibilitychange'))
  }, state)
}

test('Notes uses 15s polling and mutation invalidation refetches immediately', async (
  { page },
  testInfo,
) => {
  test.skip(testInfo.project.name !== 'desktop', 'Run timing measurement once')
  test.setTimeout(45_000)
  let getCount = 0
  let postCount = 0
  const notes: Array<{
    id: string
    title: string | null
    body_md: string | null
    is_private: boolean
    items: []
  }> = []

  await page.route('**/api/notes**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const method = request.method()
    if (path === '/api/notes' && method === 'GET') {
      getCount += 1
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: notes }),
      })
      return
    }
    if (path === '/api/notes' && method === 'POST') {
      postCount += 1
      const payload = JSON.parse(request.postData() ?? '{}') as {
        id?: string
        title?: string | null
        body_md?: string | null
        is_private?: boolean
      }
      const created = {
        id: payload.id ?? `note-${Date.now()}`,
        title: payload.title ?? null,
        body_md: payload.body_md ?? null,
        is_private: payload.is_private ?? false,
        items: [] as [],
      }
      notes.push(created)
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(created),
      })
      return
    }
    await route.fulfill({ status: 404 })
  })

  await page.goto('/')
  await page.getByRole('tab', { name: 'Ghi chú' }).click()
  await expect(page.getByText('Chưa có ghi chú.')).toBeVisible()

  getCount = 0
  await page.waitForTimeout(FAST_POLL_GUARD_MS)
  expect(getCount).toBe(0)
  await page.waitForTimeout(STANDARD_PROBE_MS - FAST_POLL_GUARD_MS)
  expect(getCount).toBe(1)

  getCount = 0
  const mutationStartedAt = Date.now()
  await page.getByTestId('quick-add-note-input').fill('Ghi chú polling synthetic')
  await page.getByTestId('quick-add-note-submit').click()
  await expect.poll(() => postCount).toBe(1)
  await expect.poll(() => getCount).toBe(1)
  expect(Date.now() - mutationStartedAt).toBeLessThan(5_000)
})

test('Tracker uses 15s polling, pauses hidden, refetches on focus, and stops after unmount', async (
  { page, taskApi, trackerApi },
  testInfo,
) => {
  test.skip(testInfo.project.name !== 'desktop', 'Run timing measurement once')
  test.setTimeout(80_000)
  await openTrackerScreen(page)

  trackerApi.resetCounts()
  await page.waitForTimeout(FAST_POLL_GUARD_MS)
  for (const path of trackerPaths) expect(trackerApi.count('GET', path)).toBe(0)
  await page.waitForTimeout(STANDARD_PROBE_MS - FAST_POLL_GUARD_MS)
  for (const path of trackerPaths) expect(trackerApi.count('GET', path)).toBe(1)

  await setVisibility(page, 'hidden')
  trackerApi.resetCounts()
  taskApi.resetCounts()
  await page.waitForTimeout(STANDARD_PROBE_MS)
  for (const path of trackerPaths) expect(trackerApi.count('GET', path)).toBe(0)
  expect(taskApi.count('GET', '/api/me')).toBe(0)

  await setVisibility(page, 'visible')
  for (const path of trackerPaths) {
    await expect.poll(() => trackerApi.count('GET', path)).toBe(1)
  }
  await expect.poll(() => taskApi.count('GET', '/api/me')).toBe(1)

  await page.getByRole('tab', { name: 'Task' }).click()
  await expect(page.getByTestId('task-list')).toBeVisible()
  trackerApi.resetCounts()
  await page.waitForTimeout(STANDARD_PROBE_MS)
  for (const path of trackerPaths) expect(trackerApi.count('GET', path)).toBe(0)
})

test('Subscription route polls exactly its three queries every 15s', async (
  { page, taskApi, trackerApi },
  testInfo,
) => {
  test.skip(testInfo.project.name !== 'desktop', 'Run timing measurement once')
  test.setTimeout(35_000)
  const subscriptionPaths = [
    '/api/subscriptions',
    '/api/settings',
    '/api/tracker/trackers',
  ] as const

  await page.goto('/subscription')
  await expect(page.getByTestId('subscription-screen')).toBeVisible()
  trackerApi.resetCounts()
  taskApi.resetCounts()

  await page.waitForTimeout(FAST_POLL_GUARD_MS)
  for (const path of subscriptionPaths) expect(trackerApi.count('GET', path)).toBe(0)
  await page.waitForTimeout(STANDARD_PROBE_MS - FAST_POLL_GUARD_MS)
  for (const path of subscriptionPaths) expect(trackerApi.count('GET', path)).toBe(1)
  expect(taskApi.count('GET', '/api/me')).toBe(0)
})

test('Calendar grid has no interval fanout after its initial fetches', async (
  { page, taskApi },
  testInfo,
) => {
  test.skip(testInfo.project.name !== 'desktop', 'Run timing measurement once')
  test.setTimeout(35_000)
  let calendarGets = 0

  await page.route('**/api/calendar/**', async (route) => {
    const request = route.request()
    if (request.method() === 'GET') {
      calendarGets += 1
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [] }),
      })
      return
    }
    await route.fulfill({ status: 404 })
  })

  await page.goto('/')
  await page.getByRole('tab', { name: 'Lịch' }).click()
  await expect(page.getByTestId('calendar-scroll-container')).toBeVisible()
  await expect.poll(() => calendarGets).toBeGreaterThan(0)

  calendarGets = 0
  taskApi.resetCounts()
  await page.waitForTimeout(STANDARD_PROBE_MS)
  expect(calendarGets).toBe(0)
  expect(taskApi.count('GET', '/api/tasks')).toBe(0)
  expect(taskApi.count('GET', '/api/me')).toBe(0)
})

test('App and ReminderConfirm session observers have no interval', async (
  { page, taskApi },
  testInfo,
) => {
  test.skip(testInfo.project.name !== 'desktop', 'Run timing measurement once')
  test.setTimeout(20_000)

  await page.goto('/')
  await expect(page.getByTestId('task-list')).toBeVisible()
  taskApi.resetCounts()
  await page.waitForTimeout(NO_POLL_PROBE_MS)
  expect(taskApi.count('GET', '/api/me')).toBe(0)

  await page.route('**/api/reminder-dispatch/*/confirm', async (route) => {
    await route.abort('failed')
  })
  await page.goto('/reminder-confirm?dispatch=synthetic-polling')
  await expect(page.getByTestId('reminder-confirm-retry')).toBeVisible()
  taskApi.resetCounts()
  await page.waitForTimeout(NO_POLL_PROBE_MS)
  expect(taskApi.count('GET', '/api/me')).toBe(0)
})
