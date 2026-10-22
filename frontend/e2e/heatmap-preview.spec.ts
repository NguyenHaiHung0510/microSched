import type { Locator, Page } from '@playwright/test'
import { expect, test, type TrackerApiState } from './fixtures/tracker'

const DAY = '2026-10-14'
const LONG_NOTE = 'Ghi chú đầy đủ: ĐỌC KỸ KẾT QUẢ tiếng Việt 🚲\n' + 'D'.repeat(90) + '\n' + 'Dấu tiếng Việt và nội dung dài cần xuống dòng. '.repeat(6)
const annualDay = (page: Page, day = DAY) => page.locator(`[data-testid="heatmap-year-day"][data-day="${day}"]`)
const preview = (page: Page) => page.getByTestId('heatmap-year-preview')

function seed(api: TrackerApiState) {
  Object.assign(api.trackers[0], { name: 'GPT', kind: 'general', input_mode: 'event' })
  Object.assign(api.trackers[1], { name: 'Cà phê' })
  Object.assign(api.trackers[2], { name: 'Đi bộ ' + 'Đ'.repeat(70), unit: 'km', kind: 'health' })
  const row = (id: string, tracker_id: string, time: string, note_md: string, values = {}) => ({
    id, tracker_id, occurred_at: `${DAY}T${time}:00+07:00`, note_md, amount: null, quantity: null, list_amount: null,
    created_at: `${DAY}T00:00:00Z`, updated_at: `${DAY}T00:00:00Z`, ...values,
  })
  api.entries = [
    row('event-1', 'tracker-001', '09:15', 'Thử prompt cho bài tập'),
    row('event-2', 'tracker-001', '20:40', LONG_NOTE),
    row('money-1', 'tracker-002', '08:10', 'Cà phê sáng', { amount: 35000 }),
    row('money-2', 'tracker-002', '16:05', 'Gặp bạn buổi chiều', { amount: 45000 }),
    row('quantity-1', 'tracker-003', '18:30', 'Đi bộ quanh công viên', { quantity: 2.5 }),
  ]
}

async function open(page: Page) {
  await page.goto('/')
  await page.getByRole('tab', { name: 'Theo dõi' }).click()
  await page.getByTestId('tracker-report-toggle').click()
  await expect(page.getByTestId('heatmap-summary')).toBeVisible()
  await page.getByTestId('heatmap-year').fill('2026')
  await page.getByTestId('heatmap-month').fill('2026-10')
  await page.getByTestId('tracker-heatmap').scrollIntoViewIfNeeded()
}

async function selectTracker(page: Page, name: string) {
  await page.getByTestId('heatmap-scope-tracker').click()
  await page.getByTestId('heatmap-tracker').click()
  await page.getByRole('option', { name, exact: true }).click()
}

async function screenshot(page: Page, filename: string) {
  if (process.env.HEATMAP_EVIDENCE_DIR) await page.screenshot({ path: `${process.env.HEATMAP_EVIDENCE_DIR}/${filename}.png` })
}

async function fits(locator: Locator) {
  return locator.evaluate(node => {
    const rect = node.getBoundingClientRect()
    return rect.left >= 0 && rect.right <= window.innerWidth && rect.top >= 0 && rect.bottom <= window.innerHeight && node.scrollWidth <= node.clientWidth
  })
}

test.beforeEach(async ({ trackerApi, page }) => {
  seed(trackerApi)
  await page.clock.setFixedTime(new Date('2026-10-20T05:00:00Z'))
})

test.afterEach(async ({ trackerApi }, info) => {
  await info.attach('synthetic-api-counts', { body: JSON.stringify(trackerApi.counts), contentType: 'application/json' })
})

test('annual hover is lazy, grouped, complete and interactive; click preserves records drilldown', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop', 'Annual view is desktop; mobile uses the existing month controls.')
  const requests: URL[] = []
  page.on('request', request => { const url = new URL(request.url()); if (url.pathname === '/api/tracker/entries' && url.searchParams.get('limit') === '51' && url.searchParams.get('order') === 'asc') requests.push(url) })
  await open(page)
  expect(requests).toHaveLength(0)
  await annualDay(page).hover()
  await expect(preview(page).getByTestId('heatmap-detail-group')).toHaveCount(3)
  await expect(preview(page).getByTestId('heatmap-detail-entry')).toHaveCount(5)
  await expect(preview(page).getByTestId('heatmap-detail-count')).toHaveText('5 lần ghi · 3 tracker')
  await expect(preview(page)).toContainText('80.000 ₫')
  await expect(preview(page)).toContainText('2,5 km')
  await expect(preview(page)).toContainText('2 lần')
  await expect(preview(page)).toContainText('08:10')
  await expect(preview(page).locator('[data-entry-id="event-2"]')).toContainText(LONG_NOTE)
  expect(requests).toHaveLength(1)
  expect(requests[0].searchParams.get('from')).toBe(`${DAY}T00:00:00+07:00`)
  expect(requests[0].searchParams.get('to')).toBe('2026-10-15T00:00:00+07:00')
  expect(await fits(preview(page))).toBe(true)
  const metrics = await preview(page).locator('p,span,button').evaluateAll(nodes => nodes.filter(node => node.getClientRects().length).map(node => parseFloat(getComputedStyle(node).fontSize)))
  expect(Math.min(...metrics)).toBeGreaterThanOrEqual(12)
  await screenshot(page, 'all-trackers-long-desktop')
  await preview(page).hover()
  await expect(preview(page)).toBeVisible()
  await preview(page).getByTestId('heatmap-detail-jump').click()
  await expect(page.getByTestId('records-mode')).toContainText('Theo ngày')
  await expect(page.getByTestId('records-date')).toHaveValue(DAY)
  await expect(page.getByTestId('records-tracker')).toContainText('Tất cả tracker')
})

test('single tracker respects actual event or quantity configuration', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop', 'Annual view is desktop.')
  await open(page)
  await selectTracker(page, 'GPT')
  await page.getByTestId('tracker-heatmap').evaluate(node => node.scrollIntoView({ block: 'start' }))
  await annualDay(page).hover()
  await expect(preview(page).getByTestId('heatmap-detail-group')).toHaveCount(1)
  await expect(preview(page).getByTestId('heatmap-detail-entry')).toHaveCount(2)
  await expect(preview(page)).toContainText('Thói quen')
  await expect(preview(page)).not.toContainText('Cà phê')
  await screenshot(page, 'single-event-desktop')
  await page.keyboard.press('Escape')
  await selectTracker(page, 'Đi bộ ' + 'Đ'.repeat(70))
  await annualDay(page).focus()
  await expect(preview(page).getByTestId('heatmap-detail-entry')).toHaveCount(1)
  await expect(preview(page)).toContainText('Sức khỏe')
  await expect(preview(page)).toContainText('2,5 km')
  await screenshot(page, 'single-quantity-desktop')
  await annualDay(page).press('Enter')
  await expect(page.getByTestId('records-tracker')).toContainText('Đi bộ')
})

test('H2 group scope matches counts, details and record drilldown; empty group stays empty', async ({ page, trackerApi }, info) => {
  trackerApi.groups = [
    {id:'scope-a',name:'Nhóm học tập',kind:'general',tracker_count:2},
    {id:'empty',name:'Nhóm trống',kind:'general',tracker_count:0},
  ]
  Object.assign(trackerApi.trackers[0], {group_id:'scope-a'})
  Object.assign(trackerApi.trackers[1], {group_id:'scope-a'})
  await open(page)
  await page.getByTestId('heatmap-scope-group').click()
  await expect(page.getByTestId('heatmap-group')).toContainText('Nhóm học tập')
  await expect(page.getByTestId('heatmap-summary')).toContainText('4 lần ghi')
  if (info.project.name === 'desktop') {
    await annualDay(page).hover()
    await expect(preview(page).getByTestId('heatmap-detail-entry')).toHaveCount(4)
    await expect(preview(page)).not.toContainText('Đi bộ')
    await preview(page).getByTestId('heatmap-detail-jump').click()
  } else {
    await page.locator(`[data-testid="heatmap-day"][data-day="${DAY}"]`).tap()
    await expect(page.getByTestId('heatmap-touch-detail').getByTestId('heatmap-detail-entry')).toHaveCount(4)
    await page.getByTestId('heatmap-touch-detail').getByTestId('heatmap-detail-jump').click()
  }
  await expect(page.getByTestId('records-group-scope')).toContainText('Nhóm học tập')
  await expect(page.getByTestId('records-list').getByTestId('entry-row')).toHaveCount(4)
  await page.getByTestId('heatmap-group').click()
  await page.getByRole('option', {name:'Nhóm trống · 0 tracker',exact:true}).click()
  await expect(page.getByTestId('heatmap-summary')).toContainText('0 lần ghi')
  await page.getByTestId('heatmap-scope-all').click()
  await expect(page.getByTestId('heatmap-summary')).toContainText('5 lần ghi')
  await expect(page.getByTestId('heatmap-group')).toHaveCount(0)
  await expect(page.getByTestId('heatmap-month')).toHaveValue('2026-10')
})

test('H2 empty group inventory provides a safe selector state and operable keyboard modes', async ({ page, trackerApi }) => {
  trackerApi.groups = []
  await open(page)
  await page.getByTestId('heatmap-scope-group').focus()
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('heatmap-scope-group')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('heatmap-group')).toBeDisabled()
  await expect(page.getByTestId('tracker-heatmap')).toContainText('Chọn một nhóm hiện có')
  await expect(page.getByTestId('heatmap-summary')).toHaveCount(0)
  await page.getByTestId('heatmap-scope-all').focus()
  await page.keyboard.press('Space')
  await expect(page.getByTestId('heatmap-summary')).toContainText('5 lần ghi')
})

test('one annual tab stop, arrow navigation, content focus and Escape', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop', 'Annual view is desktop.')
  await open(page)
  await expect(page.locator('[data-testid="heatmap-year-day"][tabindex="0"]')).toHaveCount(1)
  await annualDay(page).focus()
  await expect(preview(page).getByTestId('heatmap-detail-entry')).toHaveCount(5)
  await page.keyboard.press('ArrowLeft')
  await expect(annualDay(page, '2026-10-07')).toBeFocused()
  await page.keyboard.press('ArrowDown')
  await expect(annualDay(page, '2026-10-08')).toBeFocused()
  await page.keyboard.press('Home')
  await expect(annualDay(page, '2026-01-01')).toBeFocused()
  await page.keyboard.press('End')
  await expect(annualDay(page, '2026-10-20')).toBeFocused()
  await annualDay(page).focus()
  await page.keyboard.press('F2')
  await expect(preview(page).getByTestId('heatmap-detail-entries')).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(preview(page)).toHaveCount(0)
  await expect(annualDay(page)).toBeFocused()
  await expect(page.locator('[data-testid="heatmap-year-day"][tabindex="0"]')).toHaveCount(1)
})

test('empty and future days make no detail request; loading and errors are explicit and retryable', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop', 'Annual view is desktop.')
  let calls = 0
  let fail = true
  let release!: () => void
  const deferred = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/tracker/entries?*', async route => {
    if (new URL(route.request().url()).searchParams.get('order') !== 'asc') return route.fallback()
    calls++
    if (fail) { await deferred; return route.fulfill({ status: 503, json: { detail: 'synthetic detail failure' } }) }
    return route.fallback()
  })
  await open(page)
  await annualDay(page, '2026-10-13').focus()
  await expect(preview(page)).toContainText('Chưa có bản ghi')
  expect(calls).toBe(0)
  await page.keyboard.press('Escape')
  await annualDay(page, '2026-10-21').hover()
  await expect(preview(page)).toHaveCount(0)
  await expect(annualDay(page, '2026-10-21')).toHaveAttribute('aria-disabled', 'true')
  expect(calls).toBe(0)
  await annualDay(page).focus()
  await expect(preview(page).getByTestId('heatmap-detail-loading')).toBeVisible()
  release()
  await expect(preview(page).getByTestId('heatmap-detail-error')).toBeVisible({ timeout: 15000 })
  await screenshot(page, 'detail-error-desktop')
  fail = false
  await preview(page).getByTestId('heatmap-detail-retry').click()
  await expect(preview(page).getByTestId('heatmap-detail-entry')).toHaveCount(5)
})

test('busy day loads bounded pages on demand and updates partial group totals', async ({ page, trackerApi }, info) => {
  test.skip(info.project.name !== 'desktop', 'Annual view is desktop.')
  trackerApi.entries = Array.from({ length: 55 }, (_, index) => ({ ...trackerApi.entries[0], id: `paged-${index.toString().padStart(2, '0')}`, note_md: `Synthetic row ${index}` }))
  await open(page)
  await annualDay(page).focus()
  await expect(preview(page).getByTestId('heatmap-detail-entry')).toHaveCount(50)
  await expect(preview(page)).toContainText('50/55')
  await preview(page).getByTestId('heatmap-detail-more').click()
  await expect(preview(page).getByTestId('heatmap-detail-entry')).toHaveCount(55)
  await expect(preview(page).getByTestId('heatmap-group-total')).toHaveText('55 lần')
  await expect(preview(page).getByTestId('heatmap-detail-more')).toHaveCount(0)
})

test('switching tracker cancels stale day details', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop', 'Annual view is desktop.')
  let release!: () => void
  const deferred = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/tracker/entries?*', async route => {
    if (new URL(route.request().url()).searchParams.get('order') !== 'asc') return route.fallback()
    await deferred
    await route.fallback()
  })
  await open(page)
  await annualDay(page).focus()
  await expect(preview(page).getByTestId('heatmap-detail-loading')).toBeVisible()
  await selectTracker(page, 'GPT')
  release()
  await expect(preview(page)).toHaveCount(0)
  await annualDay(page).focus()
  await expect(preview(page).getByTestId('heatmap-detail-entry')).toHaveCount(2)
  await expect(preview(page)).not.toContainText('Cà phê')
})

test('locking privacy removes the open preview and pending private payload', async ({ page, trackerApi }, info) => {
  test.skip(info.project.name !== 'desktop', 'Annual view is desktop.')
  trackerApi.trackers[0].is_private = true
  let release!: () => void
  const deferred = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/tracker/entries?*', async route => {
    if (new URL(route.request().url()).searchParams.get('order') !== 'asc') return route.fallback()
    await deferred
    await route.fallback()
  })
  await open(page)
  await selectTracker(page, 'GPT')
  await annualDay(page).focus()
  await expect(preview(page).getByTestId('heatmap-detail-loading')).toBeVisible()
  await page.getByTestId('private-lock-now').click()
  release()
  await expect(preview(page)).toHaveCount(0)
  await expect(page.getByTestId('heatmap-scope-all')).toHaveAttribute('aria-pressed', 'true')
  await annualDay(page).focus()
  await expect(preview(page).getByTestId('heatmap-detail-group')).toHaveCount(2)
  await expect(preview(page)).not.toContainText('GPT')
  await expect(preview(page)).not.toContainText(LONG_NOTE)
})

test('month touch detail and full-record action remain available at 390px', async ({ page }, info) => {
  test.skip(info.project.name !== 'mobile', 'Touch fallback is tested with isolated Chromium mobile emulation.')
  await open(page)
  await expect(page.getByTestId('heatmap-year-overview')).toBeHidden()
  await page.locator(`[data-testid="heatmap-day"][data-day="${DAY}"]`).tap()
  const detail = page.getByTestId('heatmap-touch-detail')
  await expect(detail).toBeVisible()
  await expect(detail.getByTestId('heatmap-detail-entry')).toHaveCount(5)
  expect(await fits(detail)).toBe(true)
  await screenshot(page, 'month-touch-390')
  await detail.getByTestId('heatmap-detail-jump').click()
  await expect(detail).toBeHidden()
  await expect(page.getByTestId('records-mode')).toContainText('Theo ngày')
  await expect(page.getByTestId('records-date')).toHaveValue(DAY)
})

test('ordinary B composition shows separate money and event groups in the current app', async ({ page, trackerApi }, info) => {
  test.skip(info.project.name !== 'desktop', 'Annual view is desktop.')
  trackerApi.entries = trackerApi.entries.filter(entry => entry.tracker_id !== 'tracker-003')
  trackerApi.entries.find(entry => entry.id === 'event-2')!.note_md = 'Đọc lại kết quả và ghi chú'
  await open(page)
  await annualDay(page).hover()
  await expect(preview(page).getByTestId('heatmap-detail-entry')).toHaveCount(4)
  expect(await fits(preview(page))).toBe(true)
  await screenshot(page, 'all-trackers-ordinary-desktop')
  await page.keyboard.press('Escape')
  await selectTracker(page, 'GPT')
  await page.getByTestId('tracker-heatmap').evaluate(node => node.scrollIntoView({ block: 'start' }))
  await annualDay(page).focus()
  await expect(preview(page).getByTestId('heatmap-detail-entry')).toHaveCount(2)
  await screenshot(page, 'single-event-ordinary-desktop')
})
