import { type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { expect, fixtureTasks, test } from './fixtures/tasks'

const openTasks = fixtureTasks.filter((entry) => entry.status === 'open')
const overdueTasks = fixtureTasks.filter(
  (entry) =>
    entry.status === 'open' &&
    entry.due_at !== null &&
    new Date(entry.due_at).getTime() < Date.now(),
)
const MEASUREMENT_MS = 60_000

mkdirSync('output/playwright', { recursive: true })

async function openTasksScreen(page: Page) {
  await page.goto('/')
  await expect(page.getByTestId('task-list')).toBeVisible()
}

test('smoke renders every open task from the fixture', async ({ page }) => {
  await openTasksScreen(page)
  await expect(page.getByTestId('task-card')).toHaveCount(openTasks.length)
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

test('overdue banner selects overdue view and shows an active escape chip', async ({ page }) => {
  await openTasksScreen(page)
  await page.getByTestId('overdue-banner').click()
  await expect(page.getByTestId('filter-overdue')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('task-card')).toHaveCount(overdueTasks.length)
  for (const entry of overdueTasks) {
    await expect(page.locator(`[data-task-id="${entry.id}"]`)).toBeVisible()
  }
})

test('pinned completed tasks do not leak into open or overdue views', async ({ page }) => {
  await openTasksScreen(page)
  await expect(page.getByTestId('filter-open')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('[data-task-id="task-002"]')).toHaveCount(0)
  await page.getByTestId('overdue-banner').click()
  await expect(page.locator('[data-task-id="task-002"]')).toHaveCount(0)
})

test('completing the final overdue task returns to open view', async ({ page }) => {
  await openTasksScreen(page)
  await page.getByTestId('overdue-banner').click()
  const overdueCards = page.getByTestId('task-card')
  while ((await overdueCards.count()) > 1) {
    const before = await overdueCards.count()
    await overdueCards.first().getByTestId('task-checkbox').click()
    await expect(overdueCards).toHaveCount(before - 1)
  }
  await expect(overdueCards).toHaveCount(1)
  const finalOverdueId = await overdueCards.first().getAttribute('data-task-id')
  expect(finalOverdueId).not.toBeNull()
  if (!finalOverdueId) return
  await overdueCards.first().getByTestId('task-checkbox').click()
  await expect(page.getByTestId('filter-open')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('filter-overdue')).toBeHidden()
  await expect(page.locator(`[data-task-id="${finalOverdueId}"]`)).toHaveCount(0)
})

test('quick add posts once and clears the input', async ({ page, taskApi }) => {
  await openTasksScreen(page)
  const input = page.getByTestId('quick-add-input')
  await input.fill('Việc thêm nhanh')
  await page.getByTestId('quick-add-submit').click()
  await expect.poll(() => taskApi.count('POST', '/api/tasks')).toBe(1)
  await expect(input).toHaveValue('')
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
  const lastTitle = page.locator('[data-testid="task-card"]').last().getByTestId('task-title')
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

test('healthy visible task query polls and hidden tab stops polling', async ({ page, taskApi }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'Run timing measurement once')
  // Default Playwright test timeout is 30s; this test deliberately waits
  // MEASUREMENT_MS (60s) twice, so it must raise its own budget or it always
  // times out regardless of whether the polling behaviour is correct.
  test.setTimeout(MEASUREMENT_MS * 2 + 30_000)
  await openTasksScreen(page)
  taskApi.resetCounts()
  await page.waitForTimeout(MEASUREMENT_MS)
  const focusedCount = taskApi.count('GET', '/api/tasks')
  console.log(`refetchInterval focused: ${focusedCount} GET /api/tasks in ${MEASUREMENT_MS}ms`)
  expect(focusedCount).toBeGreaterThanOrEqual(50)
  expect(focusedCount).toBeLessThanOrEqual(70)

  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' })
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  taskApi.resetCounts()
  await page.waitForTimeout(MEASUREMENT_MS)
  console.log(`refetchInterval hidden: ${taskApi.count('GET', '/api/tasks')} GET /api/tasks in ${MEASUREMENT_MS}ms`)
  expect(taskApi.count('GET', '/api/tasks')).toBe(0)
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
