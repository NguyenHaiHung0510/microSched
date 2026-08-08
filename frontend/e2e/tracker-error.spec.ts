import { expect } from '@playwright/test'

import { test } from './fixtures/tracker'

/**
 * SUB-07 regression: the tracker screen's shared error card must surface a
 * failing subscriptions/settings query too, not only groups/entries.
 *
 * The tracker fixture already registers `/api/subscriptions`; this route is
 * registered AFTER it, so it wins for the one failing test.
 */

test('SUB-07: failing subscriptions query renders the tracker error card', async ({
  page,
}) => {
  await page.route('**/api/subscriptions', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'fixture failure' }),
    })
  })

  await page.goto('/')
  await page.getByRole('tab', { name: 'Theo dõi' }).click()

  await expect(
    page.getByRole('alert').filter({ hasText: 'Không tải được dữ liệu tracker' }),
    // Query retry mặc định của TanStack (3 lần, delay tăng dần) nên isError
    // chỉ thành true sau ~8s kể từ lần fail đầu tiên.
  ).toBeVisible({ timeout: 15_000 })
})
