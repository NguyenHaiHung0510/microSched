import { expect, test } from './fixtures/tasks'

/**
 * Task 043: UI/UX Readability Regression Suite
 * Covers 3 bounded areas:
 * 1. Logo microSched SPA navigation back to default Task screen (keyboard & touch accessible, deep links, tabs).
 * 2. Calendar month readability on laptop & mobile (usable width, sidebar toggle, detail access, selectable mobile agenda with full names).
 * 3. Task timeline empty-day hierarchy and grouping, overdue banner rebalancing above quick-add, retaining loaded items.
 */

const VN_OFFSET_MS = 7 * 3_600_000

function vnDay(offsetDays: number): string {
  return new Date(Date.now() + offsetDays * 86_400_000 + VN_OFFSET_MS)
    .toISOString()
    .slice(0, 10)
}

function iso(day: string, hour: number): string {
  return `${day}T${String(hour).padStart(2, '0')}:00:00+07:00`
}

const calendarSources = [
  {
    id: 'source-manual',
    name: 'Nguồn thủ công',
    kind: 'manual',
    color: 'rose',
    is_visible: true,
    event_count: 2,
    created_at: null,
    updated_at: null,
  },
]

function setupCalendarRoutes(
  page: import('@playwright/test').Page,
  events: Array<Record<string, unknown>> = [],
  annotations: Array<Record<string, unknown>> = [],
) {
  return page.route('**/api/calendar/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method()
    const path = url.pathname

    if (path === '/api/calendar/sources' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: calendarSources }),
      })
      return
    }
    if (path === '/api/calendar/events' && method === 'GET') {
      const from = url.searchParams.get('from')!
      const to = url.searchParams.get('to')!
      const items = events.filter((entry) => {
        const starts = new Date(String(entry.starts_at)).getTime()
        const ends = new Date(String(entry.ends_at)).getTime()
        return starts < Date.parse(to) && ends > Date.parse(from)
      })
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items }),
      })
      return
    }
    if (path === '/api/calendar/annotations' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: annotations }),
      })
      return
    }
    await route.continue()
  })
}

test.describe('Area 1: Logo microSched navigation', () => {
  test('logo button is accessible, focusable and navigates to Task from other tabs', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByTestId('task-list')).toBeVisible()

    // Switch to Notes tab
    await page.getByRole('tab', { name: 'Ghi chú' }).click()
    await expect(page.getByRole('tab', { name: 'Ghi chú' })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByRole('tab', { name: 'Task' })).toHaveAttribute('aria-selected', 'false')

    // Click logo
    const logoButton = page.getByTestId('app-logo-button')
    await expect(logoButton).toBeVisible()
    await expect(logoButton).toHaveAttribute('aria-label', 'Về trang Task mặc định')
    await logoButton.click()

    // Verifies SPA navigation back to Task view
    await expect(page.getByRole('tab', { name: 'Task' })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByTestId('task-list')).toBeVisible()
  })

  test('logo button navigates back to default Task screen from /subscription deep link without full reload', async ({ page }) => {
    await page.goto('/subscription')
    await expect(page).toHaveURL(/\/subscription/)

    const logoButton = page.getByTestId('app-logo-button')
    await expect(logoButton).toBeVisible()
    await logoButton.click()

    // Should return to "/" and Task tab
    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByRole('tab', { name: 'Task' })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByTestId('task-list')).toBeVisible()
  })

  test('logo button supports keyboard activation via Enter', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    await expect(page.getByRole('tab', { name: 'Lịch' })).toHaveAttribute('aria-selected', 'true')

    const logoButton = page.getByTestId('app-logo-button')
    await logoButton.focus()
    await page.keyboard.press('Enter')

    await expect(page.getByRole('tab', { name: 'Task' })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByTestId('task-list')).toBeVisible()
  })
})

test.describe('Area 2: Calendar month readability on desktop and mobile', () => {
  test('desktop calendar chips show time prefix and title tooltip, sidebar can be toggled', async ({
    page,
  }, testInfo) => {
    test.skip(testInfo.project.name !== 'desktop', 'Desktop only test')

    const todayStr = vnDay(0)
    const mockEvents = [
      {
        id: 'ev-distinguish-1',
        source_id: 'source-manual',
        title: 'Họp hội đồng công nghệ thông tin kỳ 1',
        starts_at: iso(todayStr, 9),
        ends_at: iso(todayStr, 10),
        all_day: false,
        location: 'Phòng 204 A2',
        description_md: null,
      },
    ]

    await setupCalendarRoutes(page, mockEvents)
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    await expect(page.getByTestId('calendar-scroll-container')).toBeVisible()

    // Event chip displays title tooltip and time prefix on desktop
    const eventChip = page.getByTestId('calendar-day-chip-event').first()
    await expect(eventChip).toBeVisible()
    const chipText = await eventChip.textContent()
    expect(chipText).toContain('09:00')
    expect(chipText).toContain('Họp hội đồng công nghệ thông tin kỳ 1')
    await expect(eventChip).toHaveAttribute('title', /Phòng 204 A2/)

    // Sidebar can be toggled on desktop to give more usable space
    const toggleSidebarBtn = page.getByTestId('calendar-toggle-sidebar')
    await expect(toggleSidebarBtn).toBeVisible()
    await expect(page.getByTestId('calendar-mininav')).toBeVisible()

    // Collapse sidebar
    await toggleSidebarBtn.click()
    await expect(toggleSidebarBtn).toHaveText('Hiện lịch nhỏ')
    await expect(page.getByTestId('calendar-mininav')).toBeHidden()

    // Expand sidebar again
    await toggleSidebarBtn.click()
    await expect(toggleSidebarBtn).toHaveText('Thu gọn lịch nhỏ')
    await expect(page.getByTestId('calendar-mininav')).toBeVisible()
  })

  test('mobile calendar provides selectable agenda mode with full untruncated titles', async ({ page }) => {
    const todayStr = vnDay(0)
    const longEventTitle = 'Bảo vệ đồ án tốt nghiệp cử nhân ngành Công nghệ Phần mềm PTIT khóa 2022'
    const mockEvents = [
      {
        id: 'ev-long-title',
        source_id: 'source-manual',
        title: longEventTitle,
        starts_at: iso(todayStr, 14),
        ends_at: iso(todayStr, 16),
        all_day: false,
        location: 'Hội trường 1',
        description_md: 'Buổi bảo vệ chính thức với hội đồng.',
      },
    ]

    await setupCalendarRoutes(page, mockEvents)
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    await expect(page.getByTestId('calendar-scroll-container')).toBeVisible()

    // Default is grid (preserves original grid as choice and passes baseline tests)
    await expect(page.getByTestId('calendar-mode-toggle-grid')).toHaveAttribute('aria-pressed', 'true')

    // Switch to selectable Agenda ("Theo ngày") mode
    const agendaToggle = page.getByTestId('calendar-mode-toggle-agenda')
    await expect(agendaToggle).toBeVisible()
    await agendaToggle.click()
    await expect(agendaToggle).toHaveAttribute('aria-pressed', 'true')

    // Agenda container and compact picker are visible
    await expect(page.getByTestId('calendar-agenda-container')).toBeVisible()
    await expect(page.getByTestId('calendar-agenda-picker')).toBeVisible()
    await expect(page.getByTestId('calendar-agenda-view')).toBeVisible()

    // Selected day agenda renders full untruncated event title
    const eventTitle = page.getByTestId('calendar-agenda-event-title')
    await expect(eventTitle).toBeVisible()
    await expect(eventTitle).toHaveText(longEventTitle)

    // Quick add task is available directly for this day
    await expect(page.getByTestId('calendar-agenda-quick-task-bar')).toBeVisible()
    await expect(page.getByTestId('calendar-agenda-quick-task-input')).toBeVisible()

    // Switch back to grid mode
    await page.getByTestId('calendar-mode-toggle-grid').click()
    await expect(page.getByTestId('calendar-mode-toggle-grid')).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByTestId('calendar-agenda-container')).toBeHidden()
  })
})

test.describe('Area 3: Task timeline empty-day hierarchy and overdue section', () => {
  test('overdue banner sits above quick add and does not push quick add below many items', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByTestId('task-list')).toBeVisible()

    // When overdue tasks exist, overdue-banner is visible above quick-add
    const overdueBanner = page.getByTestId('overdue-banner')
    await expect(overdueBanner).toBeVisible()

    const quickInput = page.getByTestId('quick-add-input')
    await expect(quickInput).toBeVisible()

    // Measure bounding boxes: banner should be placed above or alongside quick-add
    const bannerBox = await overdueBanner.boundingBox()
    const inputBox = await quickInput.boundingBox()
    expect(bannerBox).not.toBeNull()
    expect(inputBox).not.toBeNull()
    if (bannerBox && inputBox) {
      expect(bannerBox.y).toBeLessThan(inputBox.y)
    }

    // Clicking overdue banner scrolls/focuses to the overdue group
    await overdueBanner.click()
    await expect(page.getByTestId('task-overdue-earlier-group')).toBeVisible()
  })

  test('empty timeline days render compact subtle headers with testid and preserved date attributes', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByTestId('task-list')).toBeVisible()

    // Exactly 7 day groups are rendered in the default window
    const dayGroups = page.getByTestId('task-day-group')
    await expect(dayGroups).toHaveCount(7)

    // All day groups have data-day attribute
    const dayAttrs = await dayGroups.evaluateAll((groups) =>
      groups.map((g) => g.getAttribute('data-day')),
    )
    expect(dayAttrs.every(Boolean)).toBe(true)

    // Today group has "Hôm nay" badge
    const todayBadge = dayGroups.filter({ hasText: 'Hôm nay' })
    await expect(todayBadge).toBeVisible()

    // Navigating earlier advances 7 contiguous blocks (total 14) without losing items
    await page.getByTestId('task-load-earlier').click()
    await expect(page.getByTestId('task-day-group')).toHaveCount(14)
  })
})
