import { expect, test } from './fixtures/tasks'

/**
 * 010b §7.11 (qa-framework.md §4): error states must degrade locally, never
 * blank the grid, and never swallow the failure. Runs in the desktop project.
 */

const VN_OFFSET_MS = 7 * 3_600_000

function vnDay(offsetDays: number): string {
  return new Date(Date.now() + offsetDays * 86_400_000 + VN_OFFSET_MS)
    .toISOString()
    .slice(0, 10)
}

function shiftMonth(offsetMonths: number): string {
  const [year, month] = vnDay(0).split('-').map(Number)
  const index = year * 12 + (month - 1) + offsetMonths
  const targetYear = Math.floor(index / 12)
  const targetMonth = (index % 12) + 1
  return `${targetYear}-${String(targetMonth).padStart(2, '0')}`
}

function jsonResponse(body: unknown, status = 200) {
  return {
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  }
}

const emptySources = jsonResponse({ items: [] })

test('one failing month shows a local error while the rest of the grid renders', async ({
  page,
}) => {
  const failingMonth = shiftMonth(1)
  await page.route('**/api/calendar/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/calendar/events') {
      const from = url.searchParams.get('from')!
      if (from.slice(0, 7) === failingMonth) {
        await route.fulfill(
          jsonResponse({ detail: 'simulated month failure' }, 500),
        )
        return
      }
      await route.fulfill(jsonResponse({ items: [] }))
      return
    }
    if (url.pathname === '/api/calendar/annotations') {
      await route.fulfill(jsonResponse({ items: [] }))
      return
    }
    if (url.pathname === '/api/calendar/sources') {
      await route.fulfill(emptySources)
      return
    }
    await route.fallback()
  })

  await page.goto('/')
  await page.getByRole('tab', { name: 'Lịch' }).click()

  await expect(page.getByTestId('calendar-month-error')).toHaveCount(1, {
    timeout: 20_000,
  })
  await expect(page.getByTestId('calendar-month-error')).toContainText(
    'Không tải được buổi của tháng này.',
  )
  await expect(page.getByTestId('calendar-day-cell').first()).toBeVisible()
  await expect(page.getByTestId('calendar-scroll-container')).toBeVisible()
})

test('an annotation failure never blocks the grid', async ({ page }) => {
  await page.route('**/api/calendar/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/calendar/annotations') {
      await route.fulfill(
        jsonResponse({ detail: 'simulated annotation failure' }, 500),
      )
      return
    }
    if (url.pathname === '/api/calendar/events') {
      await route.fulfill(jsonResponse({ items: [] }))
      return
    }
    if (url.pathname === '/api/calendar/sources') {
      await route.fulfill(emptySources)
      return
    }
    await route.fallback()
  })

  await page.goto('/')
  await page.getByRole('tab', { name: 'Lịch' }).click()

  await expect(page.getByTestId('calendar-annotations-error')).toBeVisible({
    timeout: 20_000,
  })
  await expect(page.getByTestId('calendar-day-cell').first()).toBeVisible()
  await expect(page.getByTestId('calendar-scroll-container')).toBeVisible()
})

test('going offline after a successful load shows cached data plus a freshness hint', async ({
  page,
}) => {
  let failEvents = false
  const today = vnDay(0)
  await page.route('**/api/calendar/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/calendar/events') {
      if (failEvents) {
        await route.fulfill(
          jsonResponse({ detail: 'simulated offline failure' }, 500),
        )
        return
      }
      await route.fulfill(
        jsonResponse({
          items: [
            {
              id: 'event-cached',
              source_id: 'source-manual',
              title: 'Buổi đã tải',
              starts_at: `${today}T09:00:00+07:00`,
              ends_at: `${today}T10:00:00+07:00`,
              all_day: false,
              location: null,
              description_md: null,
              created_at: null,
              updated_at: null,
            },
          ],
        }),
      )
      return
    }
    if (url.pathname === '/api/calendar/annotations') {
      await route.fulfill(jsonResponse({ items: [] }))
      return
    }
    if (url.pathname === '/api/calendar/sources') {
      await route.fulfill(emptySources)
      return
    }
    await route.fallback()
  })

  await page.goto('/')
  await page.getByRole('tab', { name: 'Lịch' }).click()
  const todayCell = page.locator(
    `[data-testid="calendar-day-cell"][data-day="${today}"]`,
  )
  await expect(todayCell).toContainText('Buổi đã tải')

  failEvents = true
  await page.getByTestId('calendar-view-toggle-list').click()
  await page.getByTestId('calendar-view-toggle-grid').click()

  await expect(page.getByTestId('calendar-stale-indicator')).toBeVisible({
    timeout: 20_000,
  })
  await expect(todayCell).toContainText('Buổi đã tải')
  await expect(page.getByTestId('calendar-scroll-container')).toBeVisible()
})
