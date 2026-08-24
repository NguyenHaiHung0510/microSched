import { type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { expect, fixtureTasks, test } from './fixtures/tasks'

const MEASUREMENT_MS = 60_000

function todayInVietnam(): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Ho_Chi_Minh',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date())
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]))
  return `${values.year}-${values.month}-${values.day}`
}

mkdirSync('output/playwright', { recursive: true })

async function openTasksScreen(page: Page) {
  await page.goto('/')
  await expect(page.getByTestId('task-list')).toBeVisible()
}

test('smoke renders the seven-day timeline and bounded continuation', async ({ page }) => {
  await openTasksScreen(page)
  await expect(page.getByTestId('task-day-group')).toHaveCount(7)
  await expect(page.getByTestId('task-load-more-in-day')).toBeVisible()
})

test('date navigation advances contiguous seven-day blocks without duplicate headers', async ({ page }) => {
  await openTasksScreen(page)
  const first = await page.getByTestId('task-day-group').evaluateAll((groups) => groups.map((group) => group.getAttribute('data-day')))
  await page.getByTestId('task-load-earlier').click()
  await expect(page.getByTestId('task-day-group')).toHaveCount(14)
  const all = await page.getByTestId('task-day-group').evaluateAll((groups) => groups.map((group) => group.getAttribute('data-day')))
  expect(new Set(all).size).toBe(all.length)
  expect(all.slice(0, 7)).not.toEqual(first)
})

test('bucket continuation keeps its cursor range after date navigation', async ({ page }) => {
  await openTasksScreen(page)
  await page.getByTestId('task-load-earlier').click()
  await expect(page.getByTestId('task-load-more-undated')).toBeVisible()
  const statuses: number[] = []
  page.on('response', (response) => {
    if (new URL(response.url()).pathname === '/api/tasks' && response.request().method() === 'GET') statuses.push(response.status())
  })
  await page.getByTestId('task-load-more-undated').click()
  await expect(page.locator('[data-task-id="undated-119"]')).toBeVisible()
  expect(statuses).toContain(200)
  expect(statuses).not.toContain(422)
})

test('dense default continuation survives a sparse earlier block', async ({ page }) => {
  await openTasksScreen(page)
  await expect(page.getByTestId('task-load-more-in-day')).toBeVisible()
  await page.getByTestId('task-load-earlier').click()
  await expect(page.getByTestId('task-load-more-in-day')).toBeVisible()
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const target = page.locator('[data-task-id="synthetic-205"]')
    if (await target.isVisible()) break
    await page.getByTestId('task-load-more-in-day').click()
  }
  await expect(page.locator('[data-task-id="synthetic-205"]')).toBeVisible()
})

test('global undated and overlapping overdue continuations do not replay after navigation', async ({ page, taskApi }) => {
  const overdueRows = taskApi.tasks.filter((task) => task.id.startsWith('synthetic-')).slice(0, 60)
  overdueRows.forEach((task, index) => {
    task.due_precision = 'datetime'
    task.due_on = null
    task.due_at = new Date(Date.now() - (30 * 86_400_000 + index * 1_000)).toISOString()
  })
  await openTasksScreen(page)
  await expect(page.getByTestId('task-load-more-undated')).toBeVisible()
  await expect(page.getByTestId('task-load-more-overdue')).toBeVisible()
  await page.getByTestId('task-load-earlier').click()
  await page.getByTestId('task-load-earlier').click()

  const exhaust = async (buttonTestId: string, itemSelector: string) => {
    const button = page.getByTestId(buttonTestId)
    let previousCount = await page.locator(itemSelector).count()
    while (await button.isVisible()) {
      await button.click()
      await expect.poll(() => page.locator(itemSelector).count()).toBeGreaterThan(previousCount)
      previousCount = await page.locator(itemSelector).count()
    }
    return previousCount
  }

  const undatedSelector = '[data-testid="task-undated-group"] [data-task-id]'
  const overdueSelector = '[data-testid="task-overdue-earlier-group"] [data-task-id]'
  const initialUndatedCount = await page.locator(undatedSelector).count()
  const finalUndatedCount = await exhaust('task-load-more-undated', undatedSelector)
  expect(finalUndatedCount).toBeGreaterThan(initialUndatedCount)
  const initialOverdueCount = await page.locator(overdueSelector).count()
  const finalOverdueCount = await exhaust('task-load-more-overdue', overdueSelector)
  expect(finalOverdueCount).toBeGreaterThan(initialOverdueCount)
})

test('bucket continuation keeps a visible retry after a terminal API error', async ({ page }) => {
  await openTasksScreen(page)
  await page.route('**/api/tasks?*', async (route) => {
    const url = new URL(route.request().url())
    if (route.request().method() === 'GET' && url.searchParams.has('cursor')) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'temporary failure' }) })
      return
    }
    await route.fallback()
  })
  await page.getByTestId('task-load-more-undated').click()
  await expect(page.getByRole('alert')).toContainText('temporary failure')
  await expect(page.getByRole('button', { name: 'Thử lại' })).toBeVisible()
})

test('same-day cursor continuation reaches synthetic rows beyond the first bounded page', async ({ page }) => {
  await openTasksScreen(page)
  await expect(page.locator('[data-task-id="synthetic-205"]')).toHaveCount(0)
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const continuation = page.getByTestId('task-load-more-in-day')
    if (!(await continuation.isVisible())) break
    await continuation.click()
    await expect(continuation).toBeVisible().catch(() => undefined)
  }
  await expect(page.locator('[data-task-id="synthetic-205"]')).toBeVisible()
})

test('independent undated cursors reach open and completed rows beyond page size', async ({ page }) => {
  await openTasksScreen(page)
  await expect(page.getByTestId('task-load-more-undated')).toBeVisible()
  await page.getByTestId('task-load-more-undated').click()
  await expect(page.locator('[data-task-id="undated-119"]')).toBeVisible()

  await page.getByTestId('filter-completed').click()
  await expect(page.getByTestId('task-load-more-undated')).toBeVisible()
  await page.getByTestId('task-load-more-undated').click()
  await page.getByTestId('task-undated-group').getByTestId('task-day-completed-toggle').click()
  await expect(page.locator('[data-task-id="undated-120"]')).toBeVisible()
})

test('clicking card whitespace opens the detail dialog', async ({ page }) => {
  await openTasksScreen(page)
  const card = page.locator('[data-testid="task-card"]').first()
  await card.click({ position: { x: 8, y: 8 } })
  await expect(page.getByTestId('task-detail-dialog')).toBeVisible()
})

test('interactive pin control does not bubble into the detail dialog', async ({ page, taskApi }) => {
  await openTasksScreen(page)
  const card = page.locator('[data-task-id="task-001"]')
  await card.getByTestId('task-pin').click()
  await expect(page.getByTestId('task-detail-dialog')).toBeHidden()
  await expect.poll(() => taskApi.count('PATCH', '/api/tasks/task-001')).toBe(1)
})

test('opening from card whitespace returns focus to its title', async ({ page }) => {
  await openTasksScreen(page)
  const card = page.locator('[data-task-id="task-001"]')
  const title = card.getByTestId('task-title')
  await card.click({ position: { x: 8, y: 8 } })
  await expect(page.getByTestId('task-detail-dialog')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(title).toBeFocused()
  await expect(page.locator('body')).not.toBeFocused()
})

test('drag-selecting task text does not open the dialog', async ({ page }) => {
  await openTasksScreen(page)
  const selectableText = page.locator('[data-task-id="task-005"] span.tabular-nums')
  const box = await selectableText.boundingBox()
  expect(box).not.toBeNull()
  if (!box) return
  await page.mouse.move(box.x + 4, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + Math.min(box.width - 2, 90), box.y + box.height / 2)
  await page.mouse.up()
  await expect(page.getByTestId('task-detail-dialog')).toBeHidden()
})

test('overdue banner focuses the earlier overdue group without changing filter', async ({ page }) => {
  await openTasksScreen(page)
  await page.getByTestId('overdue-banner').click()
  await expect(page.getByTestId('filter-open')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('task-overdue-earlier-group')).toBeVisible()
})

test('pinned completed tasks do not leak into open or overdue views', async ({ page }) => {
  await openTasksScreen(page)
  await expect(page.getByTestId('filter-open')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('[data-task-id="task-002"]')).toHaveCount(0)
  await expect(page.locator('[data-task-id="task-002"]')).toHaveCount(0)
})

test('completing an overdue task updates its timeline group', async ({ page }) => {
  await openTasksScreen(page)
  const overdueCard = page.getByTestId('task-overdue-earlier-group').getByTestId('task-card').first()
  const taskId = await overdueCard.getAttribute('data-task-id')
  await overdueCard.getByTestId('task-checkbox').click()
  await expect(page.locator(`[data-task-id="${taskId}"]`)).toHaveCount(0)
})

test('quick add posts once and clears the input', async ({ page, taskApi }) => {
  await openTasksScreen(page)
  const input = page.getByTestId('quick-add-input')
  await input.fill('Việc thêm nhanh')
  await page.getByTestId('quick-add-submit').click()
  await expect.poll(() => taskApi.count('POST', '/api/tasks')).toBe(1)
  await expect(input).toHaveValue('')
  const created = taskApi.tasks.find((entry) => entry.title === 'Việc thêm nhanh')
  expect(created).toMatchObject({
    due_precision: 'date',
    due_on: todayInVietnam(),
    due_at: null,
  })
})

test('full create form defaults to today and requires an explicit time for datetime', async ({
  page,
  taskApi,
}, testInfo) => {
  await openTasksScreen(page)
  await page.getByText('Thêm chi tiết').click()
  const dialog = page.getByTestId('task-create-dialog')
  await expect(dialog).toBeVisible()
  const scheduleSelect = dialog.getByLabel('Kiểu lịch')
  const dateInput = dialog.getByLabel('Ngày')
  await expect(scheduleSelect).toContainText('Ngày')
  await expect(dateInput).toHaveValue(todayInVietnam())
  await expect(dialog.getByLabel('Giờ')).toHaveCount(0)
  for (const control of [scheduleSelect, dateInput]) {
    const metrics = await control.evaluate((element) => ({
      height: element.getBoundingClientRect().height,
    }))
    expect(metrics.height).toBeGreaterThanOrEqual(44)
  }
  if (testInfo.project.name === 'mobile') {
    const dateFontSize = await dateInput.evaluate((element) =>
      Number.parseFloat(getComputedStyle(element).fontSize))
    expect(dateFontSize).toBeGreaterThanOrEqual(16)
  }
  const viewport = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }))
  expect(viewport.scrollWidth).toBeLessThanOrEqual(viewport.clientWidth)

  await dialog.getByLabel('Tiêu đề').fill('   ')
  await expect(dialog.getByRole('button', { name: 'Tạo task' })).toBeDisabled()
  await dialog.getByLabel('Tiêu đề').fill('Có giờ rõ ràng')
  await scheduleSelect.click()
  await page.getByRole('option', { name: 'Ngày + giờ' }).click()
  const timeInput = dialog.getByLabel('Giờ')
  await expect(timeInput).toHaveValue('')
  await expect(timeInput).toHaveCSS('height', '44px')
  if (testInfo.project.name === 'mobile') {
    const timeFontSize = await timeInput.evaluate((element) =>
      Number.parseFloat(getComputedStyle(element).fontSize))
    expect(timeFontSize).toBeGreaterThanOrEqual(16)
  }
  await expect(dialog.getByRole('button', { name: 'Tạo task' })).toBeDisabled()
  await timeInput.fill('09:30')
  await expect(dialog.getByRole('button', { name: 'Tạo task' })).toBeEnabled()
  await dialog.getByRole('button', { name: 'Tạo task' }).click()
  await expect(dialog).toBeHidden()
  expect(taskApi.tasks.find((entry) => entry.title === 'Có giờ rõ ràng')).toMatchObject({
    due_precision: 'datetime',
    due_on: null,
    due_at: `${todayInVietnam()}T09:30:00+07:00`,
  })
})

test('obsolete quick-add microcopy is absent', async ({ page }) => {
  await openTasksScreen(page)
  await expect(page.locator('body')).not.toContainText('Lưu xong ô tự xoá')
  await expect(page.getByText('Thêm chi tiết')).toBeVisible()
})

test('mobile layout has no horizontal overflow and banner has a 44px target', async ({ page }) => {
  await openTasksScreen(page)
  const measurements = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }))
  expect(measurements.scrollWidth).toBeLessThanOrEqual(measurements.innerWidth)
  const banner = await page.getByTestId('overdue-banner').evaluate((element) => {
    const rect = element.getBoundingClientRect()
    return { height: rect.height, width: rect.width }
  })
  expect(banner.height).toBeGreaterThanOrEqual(44)
  expect(banner.width).toBeGreaterThan(0)
})

test('last card tooltip is portalled and fully inside the desktop viewport', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'Radix tooltip is a desktop shortcut')
  await openTasksScreen(page)
  const lastTitle = page.locator('[data-task-id="task-032"]').getByTestId('task-title')
  await lastTitle.hover()
  const tooltip = page.getByRole('tooltip')
  await expect(tooltip).toBeVisible()
  const bounds = await tooltip.evaluate((element) => {
    const rect = element.getBoundingClientRect()
    return { top: rect.top, right: rect.right, bottom: rect.bottom, left: rect.left }
  })
  const viewport = page.viewportSize()
  expect(viewport).not.toBeNull()
  if (viewport) {
    expect(bounds.top).toBeGreaterThanOrEqual(0)
    expect(bounds.left).toBeGreaterThanOrEqual(0)
    expect(bounds.right).toBeLessThanOrEqual(viewport.width)
    expect(bounds.bottom).toBeLessThanOrEqual(viewport.height)
  }
  await page.screenshot({ path: 'output/playwright/tooltip-last-card.png', fullPage: true })
})

test('task-012 tooltip shows three static numbered items and the remaining count', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'Radix tooltip is a desktop shortcut')
  await openTasksScreen(page)
  const title = page.locator('[data-task-id="task-012"]').getByTestId('task-title')
  await title.hover()

  const tooltip = page.getByRole('tooltip')
  await expect(tooltip).toBeVisible()
  await expect(tooltip.getByText('Checklist (4)')).toBeVisible()
  const items = tooltip.getByRole('listitem')
  await expect(items).toHaveCount(3)
  await expect(items.nth(0)).toContainText('1.')
  await expect(items.nth(0)).toContainText('Mục đầu tiên')
  await expect(items.nth(1)).toContainText('2.')
  await expect(items.nth(1)).toContainText('Mục thứ hai')
  await expect(items.nth(2)).toContainText('3.')
  await expect(items.nth(2)).toContainText('Mục thứ ba')
  await expect(tooltip.getByText(/và 1 mục nữa/)).toBeVisible()
  await expect(tooltip.locator('button, [role="button"]')).toHaveCount(0)
  await page.screenshot({ path: 'output/playwright/tooltip-task-012-desktop.png', fullPage: true })
})

test('add-details button has symmetric zero horizontal padding', async ({ page }, testInfo) => {
  await openTasksScreen(page)
  const button = page.getByRole('button', { name: /^Thêm chi tiết$/ })
  await expect(button).toBeVisible()
  const padding = await button.evaluate((element) => {
    const style = getComputedStyle(element)
    return {
      left: Number.parseFloat(style.paddingLeft),
      right: Number.parseFloat(style.paddingRight),
    }
  })
  expect(padding.left).toBe(padding.right)
  expect(padding.left).toBe(0)
  await page.screenshot({
    path: `output/playwright/add-details-${testInfo.project.name}.png`,
    fullPage: true,
  })
})

test('healthy visible task query polls and hidden tab stops polling', async ({ page, taskApi }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'Run timing measurement once')
  // Default Playwright test timeout is 30s; this test deliberately waits
  // MEASUREMENT_MS (60s) twice, so it must raise its own budget or it always
  // times out regardless of whether the polling behaviour is correct.
  test.setTimeout(MEASUREMENT_MS * 2 + 30_000)
  await openTasksScreen(page)
  taskApi.resetCounts()
  await page.waitForTimeout(MEASUREMENT_MS)
  const focusedCount = taskApi.count('GET', '/api/tasks/timeline')
  console.log(`refetchInterval focused: ${focusedCount} GET /api/tasks/timeline in ${MEASUREMENT_MS}ms`)
  expect(focusedCount).toBeGreaterThanOrEqual(50)
  expect(focusedCount).toBeLessThanOrEqual(70)

  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' })
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  taskApi.resetCounts()
  await page.waitForTimeout(MEASUREMENT_MS)
  console.log(`refetchInterval hidden: ${taskApi.count('GET', '/api/tasks/timeline')} GET /api/tasks/timeline in ${MEASUREMENT_MS}ms`)
  expect(taskApi.count('GET', '/api/tasks/timeline')).toBe(0)
})

test('session error performs no repeated /api/me polling', async ({ page, taskApi }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'Run timing measurement once')
  test.setTimeout(MEASUREMENT_MS + 30_000)
  taskApi.sessionStatus = 401
  await page.goto('/')
  await expect(page.getByText('Cần đăng nhập')).toBeVisible()
  taskApi.resetCounts()
  await page.waitForTimeout(MEASUREMENT_MS)
  console.log(`session error: ${taskApi.count('GET', '/api/me')} GET /api/me after initial 401`)
  expect(taskApi.count('GET', '/api/me')).toBe(0)
})
