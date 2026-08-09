import { expect } from '@playwright/test'

import { fixturePrivatePin, test as tasksTest } from './fixtures/tasks'

/**
 * F8/F9 regression tests for the /reminder-confirm deep link (011b).
 *
 * Registered after the shared tasks fixture so these routes win for
 * `/api/reminder-dispatch/*`; everything else still falls back to the shared
 * session/private-gate mocks.
 */
type ConfirmState = {
  /** Statuses served in order; the last one repeats. */
  statuses: number[]
  /** Request bodies captured in arrival order. */
  bodies: Array<Record<string, unknown>>
  /** When true, the next confirm POST is aborted like a network loss. */
  abortNext: boolean
}

const test = tasksTest.extend<{ confirmApi: ConfirmState }>({
  confirmApi: [
    async ({ page }, use) => {
      const state: ConfirmState = { statuses: [200], bodies: [], abortNext: false }
      await page.route('**/api/reminder-dispatch/**', async (route) => {
        const request = route.request()
        if (request.method() !== 'POST') {
          await route.fallback()
          return
        }
        if (state.abortNext) {
          state.abortNext = false
          await route.abort('internetdisconnected')
          return
        }
        state.bodies.push(JSON.parse(request.postData() ?? '{}'))
        const status = state.statuses.shift() ?? 200
        if (status === 403) {
          await route.fulfill({
            status: 403,
            contentType: 'application/json',
            body: JSON.stringify({
              detail: {
                code: 'PRIVATE_UNLOCK_REQUIRED',
                message: 'Unlock private mode to confirm this medication reminder',
              },
            }),
          })
          return
        }
        await route.fulfill({
          status,
          contentType: 'application/json',
          body: JSON.stringify({ confirmed_entry_id: 'entry-created-1', created: true }),
        })
      })
      await use(state)
    },
    { auto: true },
  ],
})

test('F9: 403 PRIVATE_UNLOCK_REQUIRED opens the unlock flow and retries the SAME body', async ({
  page,
  confirmApi,
}) => {
  confirmApi.statuses = [403, 200]
  await page.goto('/reminder-confirm?dispatch=dispatch-001')

  // The prompt must survive: the unlock dialog opens instead of navigating away.
  const pinInput = page.getByTestId('private-pin-input')
  await expect(pinInput).toBeVisible()

  await pinInput.fill(fixturePrivatePin)
  await page.getByTestId('private-unlock-submit').click()

  // Unlock succeeded -> confirm is retried with the ORIGINAL body, then the
  // success path lands back on the home screen.
  await expect.poll(() => confirmApi.bodies.length).toBe(2)
  expect(confirmApi.bodies[0]).toEqual(confirmApi.bodies[1])
  expect(confirmApi.bodies[0]).toMatchObject({
    entry_id: expect.any(String),
    occurred_at: expect.any(String),
  })
  await expect(page).toHaveURL(/\/$/)
})

test('F9: network failure keeps the screen with guidance + retry, no navigate', async ({
  page,
  confirmApi,
}) => {
  confirmApi.abortNext = true
  await page.goto('/reminder-confirm?dispatch=dispatch-001')

  // Still on the deep link: the reminder was NOT swallowed.
  await expect(page).toHaveURL(/\/reminder-confirm\?dispatch=dispatch-001$/)
  await expect(page.getByText(/Không kết nối được máy chủ/)).toBeVisible()

  const retry = page.getByTestId('reminder-confirm-retry')
  await expect(retry).toBeVisible()
  // iPhone primary action: HIG touch target must stay at least 44px even if
  // the Button size variant changes later.
  const retryBox = await retry.boundingBox()
  expect(retryBox?.height).toBeGreaterThanOrEqual(44)
  await retry.click()

  await expect.poll(() => confirmApi.bodies.length).toBe(1)
  await expect(page).toHaveURL(/\/$/)
})

test('F8: login link carries a relative return_to so the reminder prompt is not lost', async ({
  page,
  taskApi,
}) => {
  taskApi.sessionStatus = 401
  await page.goto('/reminder-confirm?dispatch=dispatch-001')

  const link = page.getByTestId('login-link')
  await expect(link).toBeVisible()
  const href = await link.getAttribute('href')
  expect(href).toContain('/auth/login?return_to=')

  const returnTo = decodeURIComponent(String(href).split('return_to=')[1])
  expect(returnTo).toBe('/reminder-confirm?dispatch=dispatch-001')
  // Open-redirect guardrails: path only, never an origin or protocol-relative URL.
  expect(returnTo.startsWith('http')).toBe(false)
  expect(returnTo.startsWith('//')).toBe(false)
  expect(returnTo.startsWith('://')).toBe(false)
})
