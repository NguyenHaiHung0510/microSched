import { test, expect } from './fixtures/tracker'

for (const scenario of [
  { name: 'first-day', days: 0, current: 300000, previous: 0, summary: 'Chưa đủ kỳ so sánh', report: 'Chưa đủ kỳ so sánh' },
  { name: 'signed', days: 6, current: -100, previous: -300, summary: 'tăng 200', report: 'Nhiều hơn 200' },
]) {
  test(`overview and detailed comparison agree for ${scenario.name}`, async ({ page }) => {
    await page.route('**/api/tracker/dashboard?*', (route) => route.fulfill({ json: {
      period_start: '2026-09-01T00:00:00+07:00', period_end: '2026-09-07T12:00:00+07:00', current_period_days: scenario.days, prev_period_days: scenario.days, prev_period_truncated: false,
      corrupted_entry_count: 0, f1_total: scenario.current, f2_current: scenario.current, f2_previous: scenario.previous, f5_net: -scenario.current,
      report_months: 1, previous_period_start: '2026-08-01T00:00:00+07:00', previous_period_end: '2026-09-01T00:00:00+07:00',
      finance_months: [{ month: '2026-09', period_start: '2026-09-01T00:00:00+07:00', period_end: '2026-09-07T12:00:00+07:00', total: scenario.current }], activity_month: '2026-09', activity_days: [],
      f3_groups: [], f4_top: [], a2_gap: [], a3_counts: { week: 0, month: 0, year: 0 }, a4_trend: { current_month: 0, prev_avg: 0, trend: 'flat' },
      f6: { monthly_burn: 0, subscription_count: 0, corrupted_subscription_count: 0, upcoming: [] },
    } }))
    await page.goto('/')
    await page.getByRole('tab', { name: 'Theo dõi' }).click()
    await expect(page.getByTestId('tracker-finance-compare')).toContainText(scenario.summary)
    await page.getByTestId('tracker-open-report').click()
    await expect(page.getByTestId('dashboard-f2-compare')).toContainText(scenario.report)
  })
}

test('finance charts show exact periods, composition and keyboard disclosure without overflow', async ({ page }) => {
  await page.route('**/api/tracker/dashboard?*', (route) => route.fulfill({ json: {
    period_start: '2026-08-01T00:00:00+07:00', period_end: '2026-09-01T00:00:00+07:00', current_period_days: 31, prev_period_days: 31, prev_period_truncated: false,
    corrupted_entry_count: 0, f1_total: 1800000, f2_current: 1800000, f2_previous: 2100000, f5_net: -1800000,
    report_months: 1, previous_period_start: '2026-07-01T00:00:00+07:00', previous_period_end: '2026-08-01T00:00:00+07:00',
    finance_months: [{ month: '2026-08', period_start: '2026-08-01T00:00:00+07:00', period_end: '2026-09-01T00:00:00+07:00', total: 1800000 }], activity_month: '2026-08', activity_days: [],
    f3_groups: [{ name: 'Nhóm ' + 'X'.repeat(70), total: 1800000, trackers: [{ tracker_id: 'tracker-002', name: '', total: 1800000 }] }],
    f4_top: [], a2_gap: [], a3_counts: { week: 1, month: 2, year: 3 }, a4_trend: { current_month: 2, prev_avg: 3, trend: 'down' },
    f6: { monthly_burn: 0, subscription_count: 0, corrupted_subscription_count: 0, upcoming: [] },
  } }))
  await page.goto('/')
  await page.getByRole('tab', { name: 'Theo dõi' }).click()
  await page.getByTestId('tracker-report-month').fill('2026-08')
  await page.getByTestId('tracker-open-report').click()
  const comparison = page.getByTestId('dashboard-finance-comparison')
  await expect(comparison).toContainText('1.800.000')
  await expect(comparison).toContainText('2.100.000')
  await expect(comparison).toContainText('01/08/2026')
  await expect(comparison).toContainText('01/07/2026')
  // Common currency totals remain on one readable line at either viewport.
  expect((await page.getByTestId('dashboard-f1-total').boundingBox())?.height).toBeLessThan(40)
  const group = page.getByTestId('dashboard-f3-group')
  await group.locator('summary').focus()
  await page.keyboard.press('Enter')
  await expect(group).toHaveAttribute('open', '')
  await expect(group.locator('dt')).toHaveText('Ăn uống')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  const rect = await group.locator('summary').boundingBox()
  expect(rect?.height).toBeGreaterThanOrEqual(44)
})

test('failed financial request reports error instead of empty spending', async ({ page }) => {
  await page.route('**/api/tracker/dashboard?*', (route) => route.fulfill({ status: 500, json: { detail: 'Synthetic unavailable' } }))
  await page.goto('/')
  await page.getByRole('tab', { name: 'Theo dõi' }).click()
  await expect(page.getByTestId('app-live-status')).toHaveAttribute('data-state', 'error', { timeout: 15_000 })
  await expect(page.getByTestId('tracker-finance-total')).toHaveCount(0)
  await page.getByTestId('tracker-open-report').click()
  await expect(page.getByTestId('dashboard-error')).toBeVisible()
})
