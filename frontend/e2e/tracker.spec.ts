import { type Page } from '@playwright/test'
import { expect, test, type TrackerApiState } from './fixtures/tracker'

async function openTrackerScreen(page: Page) {
  await page.goto('/')
  await page.getByRole('tab', { name: 'Theo dõi' }).click()
  await expect(page.getByTestId('tracker-grid')).toBeVisible()
}

test('smoke renders the capture grid with last-seen labels', async ({ page }) => {
  await openTrackerScreen(page)
  await expect(page.getByTestId('tracker-button')).toHaveCount(3)
  await expect(
    page.locator('[data-testid="tracker-last-seen"][data-tracker-id="tracker-001"]'),
  ).toContainText('ngày trước')
  await expect(
    page.locator('[data-testid="tracker-last-seen"][data-tracker-id="tracker-002"]'),
  ).toContainText('giờ trước')
})

test('one-tap capture creates one entry and offers a 10s undo', async ({
  page,
  trackerApi,
}) => {
  await openTrackerScreen(page)
  await page.locator('[data-testid="tracker-button"][data-tracker-id="tracker-001"]').click()
  await expect.poll(() => trackerApi.count('POST', '/api/tracker/entries')).toBe(1)
  await expect(page.getByRole('button', { name: 'Hoàn tác' })).toBeVisible()
})

test('money input echoes the exact formatted number that will be sent', async ({
  page,
  trackerApi,
}) => {
  await openTrackerScreen(page)
  await page.locator('[data-testid="tracker-button"][data-tracker-id="tracker-002"]').click()
  const input = page.getByTestId('tracker-amount-input')
  await expect(input).toBeVisible()
  await input.fill('100000')
  await expect(page.getByText('= 100.000 ₫')).toBeVisible()
  await page.getByTestId('tracker-backdate-dialog').count()
  await page.locator('[data-tracker-id="tracker-002"]').getByRole('button', { name: 'Ghi' }).click()
  await expect.poll(() => trackerApi.count('POST', '/api/tracker/entries')).toBe(1)
  expect(trackerApi.entries[0].amount).toBe(100000)
})

test('long-press backdates exactly one entry — the synthetic click is suppressed', async ({
  page,
  trackerApi,
}) => {
  await openTrackerScreen(page)

  await page.evaluate(() => {
    const el = document.querySelector(
      '[data-testid="tracker-button"][data-tracker-id="tracker-001"]',
    ) as HTMLElement
    const touch = new Touch({ identifier: 1, target: el, clientX: 40, clientY: 40 })
    el.dispatchEvent(
      new TouchEvent('touchstart', { touches: [touch], bubbles: true, cancelable: true }),
    )
  })
  await page.waitForTimeout(650)
  await page.evaluate(() => {
    const el = document.querySelector(
      '[data-testid="tracker-button"][data-tracker-id="tracker-001"]',
    ) as HTMLElement
    const touch = new Touch({ identifier: 1, target: el, clientX: 40, clientY: 40 })
    el.dispatchEvent(
      new TouchEvent('touchend', {
        touches: [],
        changedTouches: [touch],
        bubbles: true,
        cancelable: true,
      }),
    )
  })

  const dialog = page.getByTestId('tracker-backdate-dialog')
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Ghi' }).click()

  // The one-tap path must NOT fire on top of the backdate path (§5.3).
  await expect.poll(() => trackerApi.count('POST', '/api/tracker/entries')).toBe(1)
  const created = trackerApi.entries[0]
  expect(created.occurred_at).toMatch(/\+07:00$/)
})

export type { TrackerApiState }
