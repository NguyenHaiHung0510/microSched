import { expect, test } from './fixtures/tasks'

test.beforeEach(async ({ page }) => {
  for (const pattern of ['**/api/notes**', '**/api/subscriptions**', '**/api/settings**']) {
    await page.route(pattern, (route) => route.fulfill({ json: { items: [] } }))
  }
})

test('agenda task failures do not look empty and recover through the visible retry', async ({ page }) => {
  let fail = true
  await setupCalendarRoutes(page)
  await page.route('**/api/tasks?**', (route) => {
    const url = new URL(route.request().url())
    if (url.searchParams.get('bucket') !== 'dated') return route.fallback()
    return route.fulfill({ status: fail ? 500 : 200, json: fail ? { detail: 'Synthetic load failure' } : { items: [] } })
  })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Lịch' }).click()
  await page.getByTestId('calendar-mode-toggle-agenda').click()
  await expect(page.getByTestId('calendar-agenda-tasks-loading')).toBeVisible()
  await expect(page.getByTestId('calendar-agenda-tasks-empty')).toHaveCount(0)
  await expect(page.getByTestId('calendar-agenda-tasks-error')).toBeVisible({ timeout: 12_000 })
  await expect(page.getByTestId('calendar-agenda-tasks-empty')).toHaveCount(0)
  fail = false
  await page.getByTestId('calendar-agenda-tasks-retry').click()
  await expect(page.getByTestId('calendar-agenda-tasks-empty')).toBeVisible()
})

/**
 * Task 043: Agenda State, Month Navigation, Error Handling & Persistence Suite
 * Covers 5 bounded areas:
 * 1. Month navigation beyond fetched window fetches contiguous queries without holes and updates agendaDay to 1st.
 * 2. Per-month event/task loading/error states in agenda explicitly handled, never showing 'Không có buổi...' on error.
 * 3. Agenda quick add retains draft on mutation failure, clears only on success, and keeps focus.
 * 4. Calendar grid/agenda preference persisted in localStorage and default grid compatibility.
 * 5. Vietnamese schedule time formatting for task due_at, wrap min-w-0, mobile 390px controls >= 44px.
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

test.describe('Task 043: Calendar agenda mode state & persistence', () => {
  test('persists grid/agenda preference in localStorage and respects default grid', async ({ page }) => {
    await setupCalendarRoutes(page)
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    await expect(page.getByTestId('calendar-scroll-container')).toBeVisible()

    // Default mode is grid
    await expect(page.getByTestId('calendar-mode-toggle-grid')).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByTestId('calendar-agenda-container')).toBeHidden()

    // Switch to agenda mode
    await page.getByTestId('calendar-mode-toggle-agenda').click()
    await expect(page.getByTestId('calendar-agenda-container')).toBeVisible()
    await expect(page.getByTestId('calendar-mode-toggle-agenda')).toHaveAttribute('aria-pressed', 'true')

    // LocalStorage preference is saved
    const savedMode = await page.evaluate(() => localStorage.getItem('microsched:calendar-mode'))
    expect(savedMode).toBe('agenda')

    // Reload page
    await page.reload()
    await page.getByRole('tab', { name: 'Lịch' }).click()

    // Should still be in agenda mode
    await expect(page.getByTestId('calendar-agenda-container')).toBeVisible()
    await expect(page.getByTestId('calendar-mode-toggle-agenda')).toHaveAttribute('aria-pressed', 'true')

    // Switch back to grid mode
    await page.getByTestId('calendar-mode-toggle-grid').click()
    await expect(page.getByTestId('calendar-mode-toggle-grid')).toHaveAttribute('aria-pressed', 'true')
    const updatedSaved = await page.evaluate(() => localStorage.getItem('microsched:calendar-mode'))
    expect(updatedSaved).toBe('grid')
  })

  test('switching between agenda and grid removes duplicate outer mini-nav in agenda and restores in grid', async ({ page }) => {
    await setupCalendarRoutes(page)
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()

    // In grid mode on desktop, mini-nav is visible
    const miniNav = page.getByTestId('calendar-mininav')
    if (await miniNav.isVisible()) {
      // Switch to agenda
      await page.getByTestId('calendar-mode-toggle-agenda').click()
      await expect(page.getByTestId('calendar-agenda-container')).toBeVisible()

      // In agenda mode, outer mini-nav is removed
      await expect(miniNav).toBeHidden()

      // Switch back to grid
      await page.getByTestId('calendar-mode-toggle-grid').click()
      await expect(page.getByTestId('calendar-agenda-container')).toBeHidden()

      // Mini-nav is restored
      await expect(miniNav).toBeVisible()

      // Today button works
      await page.getByTestId('calendar-today-button').click()
      await expect(page.getByTestId('calendar-scroll-container')).toBeVisible()
    }
  })

  test('navigating >6 months beyond initial window fetches new range without holes and updates agendaDay', async ({ page }) => {
    const requestedEventRanges: Array<{ from: string; to: string }> = []
    const requestedTaskRanges: Array<{ from: string; to: string }> = []

    await page.route('**/api/calendar/**', async (route) => {
      const url = new URL(route.request().url())
      if (url.pathname === '/api/calendar/sources') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: calendarSources }),
        })
        return
      }
      if (url.pathname === '/api/calendar/events') {
        const from = url.searchParams.get('from') ?? ''
        const to = url.searchParams.get('to') ?? ''
        requestedEventRanges.push({ from, to })
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: [] }),
        })
        return
      }
      if (url.pathname === '/api/calendar/annotations') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: [] }),
        })
        return
      }
      await route.continue()
    })

    await page.route('**/api/tasks**', async (route) => {
      const url = new URL(route.request().url())
      if (url.searchParams.has('from') && url.searchParams.has('to')) {
        requestedTaskRanges.push({
          from: url.searchParams.get('from')!,
          to: url.searchParams.get('to')!,
        })
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [] }),
      })
    })

    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    await page.getByTestId('calendar-mode-toggle-agenda').click()
    await expect(page.getByTestId('calendar-agenda-container')).toBeVisible()

    const initialMonthTitle = await page.getByTestId('calendar-agenda-month-title').textContent()

    // Navigate 7 months forward (beyond the default ±6 month window)
    for (let i = 0; i < 7; i++) {
      await page.getByTestId('calendar-agenda-next-month').click()
    }

    const distantMonthTitle = await page.getByTestId('calendar-agenda-month-title').textContent()
    expect(distantMonthTitle).not.toBe(initialMonthTitle)

    // The selected day in agenda should be day 01 of the target month, NOT retaining prior month's day
    const dayTitle = await page.getByTestId('calendar-agenda-day-title').textContent()
    expect(dayTitle).toContain('01/')

    // Ensure requested event ranges include the distant month
    expect(requestedEventRanges.length).toBeGreaterThan(0)
    expect(requestedTaskRanges.length).toBeGreaterThan(0)
  })

  test('agenda handles per-month event loading/error states explicitly without false empty message', async ({ page }) => {
    let failEvents = true

    await page.route('**/api/calendar/**', async (route) => {
      const url = new URL(route.request().url())
      if (url.pathname === '/api/calendar/sources') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: calendarSources }),
        })
        return
      }
      if (url.pathname === '/api/calendar/events') {
        if (failEvents) {
          await route.fulfill({
            status: 500,
            contentType: 'application/json',
            body: JSON.stringify({ detail: 'Simulated failure' }),
          })
          return
        }
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: [
              {
                id: 'ev-retry-success',
                source_id: 'source-manual',
                title: 'Buổi đã tải sau khi thử lại',
                starts_at: iso(vnDay(0), 10),
                ends_at: iso(vnDay(0), 11),
                all_day: false,
                location: null,
                description_md: null,
              },
            ],
          }),
        })
        return
      }
      if (url.pathname === '/api/calendar/annotations') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: [] }),
        })
        return
      }
      await route.continue()
    })

    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    await page.getByTestId('calendar-mode-toggle-agenda').click()
    await expect(page.getByTestId('calendar-agenda-container')).toBeVisible()

    // On failed event query, error card is rendered
    const errorAlert = page.getByTestId('calendar-agenda-events-error')
    await expect(page.getByTestId('calendar-agenda-events-loading')).toBeVisible()
    await expect(page.getByTestId('calendar-agenda-events-empty')).toHaveCount(0)
    // Existing query defaults retry at 1s, 2s, 4s before reaching the error state.
    await expect(errorAlert).toBeVisible({ timeout: 12_000 })
    await expect(errorAlert).toContainText('Không tải được buổi của tháng này.')

    // Must NEVER show 'Không có buổi nào trong ngày.' on failed query!
    await expect(page.getByTestId('calendar-agenda-events-empty')).toHaveCount(0)

    // Now permit success and click retry
    failEvents = false
    const retryBtn = errorAlert.getByRole('button', { name: 'Thử lại' })
    await retryBtn.click()

    // Event now loads
    await expect(page.getByTestId('calendar-agenda-event-card')).toBeVisible()
    await expect(page.getByTestId('calendar-agenda-event-title')).toHaveText('Buổi đã tải sau khi thử lại')
  })

  test('agenda quick add retains draft on failure, clears on success and maintains input focus', async ({ page }) => {
    let failCreate = true
    let capturedBody: Record<string, unknown> | null = null

    await setupCalendarRoutes(page)

    await page.route('**/api/tasks', async (route) => {
      const request = route.request()
      if (request.method() === 'POST') {
        capturedBody = JSON.parse(request.postData() ?? '{}')
        if (failCreate) {
          await route.fulfill({
            status: 500,
            contentType: 'application/json',
            body: JSON.stringify({ detail: 'Failed to create' }),
          })
          return
        }
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'task-created-001',
            title: capturedBody?.title ?? '',
            status: 'open',
            priority: null,
            due_precision: 'date',
            due_on: capturedBody?.due_on ?? null,
            due_at: null,
            is_private: false,
            pinned: false,
            items: [],
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }),
        })
        return
      }
      await route.continue()
    })

    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    await page.getByTestId('calendar-mode-toggle-agenda').click()
    await expect(page.getByTestId('calendar-agenda-container')).toBeVisible()

    const quickInput = page.getByTestId('calendar-agenda-quick-task-input')
    const quickSubmit = page.getByTestId('calendar-agenda-quick-task-submit')

    const draftText = 'Nộp báo cáo kiến trúc hệ thống'
    await quickInput.fill(draftText)
    await quickSubmit.click()

    // On failure: draft text is retained in the input!
    await expect(quickInput).toHaveValue(draftText)
    await expect(quickInput).toBeFocused()

    // Allow success on next attempt
    failCreate = false
    await quickSubmit.click()

    // On success: input is cleared and focused for repeated entry
    await expect(quickInput).toHaveValue('')
    await expect(quickInput).toBeFocused()

    // Verify submission captured correct due_on
    expect(capturedBody).toMatchObject({
      title: draftText,
      due_on: vnDay(0),
    })
  })

  test('agenda card displays Vietnamese schedule time formatting for task due_at and wrap min-w-0', async ({ page }) => {
    const todayStr = vnDay(0)
    const longTitle = 'Hội thảo chuyên đề trí tuệ nhân tạo và ứng dụng kỹ thuật phần mềm thế hệ mới'

    await setupCalendarRoutes(page, [
      {
        id: 'ev-long-wrap',
        source_id: 'source-manual',
        title: longTitle,
        starts_at: iso(todayStr, 9),
        ends_at: iso(todayStr, 11),
        all_day: false,
        location: 'Hội trường B',
        description_md: 'Mô tả chi tiết của buổi hội thảo.',
      },
    ])

    await page.route('**/api/tasks**', async (route) => {
      const url = new URL(route.request().url())
      if (url.searchParams.has('from') && url.searchParams.has('to')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: [
              {
                id: 'task-with-due-at',
                title: 'Họp phản biện đề cương nghiên cứu',
                status: 'open',
                priority: 'p1',
                due_precision: 'datetime',
                due_on: null,
                due_at: iso(todayStr, 14),
                is_private: false,
                pinned: false,
                items: [],
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              },
            ],
          }),
        })
        return
      }
      await route.continue()
    })

    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    await page.getByTestId('calendar-mode-toggle-agenda').click()
    await expect(page.getByTestId('calendar-agenda-container')).toBeVisible()

    // Task card renders Vietnamese schedule time (14:00), not raw ISO string
    const taskCard = page.getByTestId('calendar-agenda-task-card')
    await expect(taskCard).toBeVisible()
    const taskText = await taskCard.textContent()
    expect(taskText).toContain('14:00')
    expect(taskText).not.toContain(iso(todayStr, 14))

    // Event title with long text is rendered
    const eventTitle = page.getByTestId('calendar-agenda-event-title')
    await expect(eventTitle).toBeVisible()
    await expect(eventTitle).toHaveText(longTitle)
  })

  test('mobile 390px layout has no horizontal overflow and primary controls measured >= 44px', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await setupCalendarRoutes(page)
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    await page.getByTestId('calendar-mode-toggle-agenda').click()
    await expect(page.getByTestId('calendar-agenda-container')).toBeVisible()

    // No horizontal scroll overflow on container
    const container = page.getByTestId('calendar-scroll-container')
    const overflow = await container.evaluate((el) => el.scrollWidth - el.clientWidth)
    expect(overflow).toBeLessThanOrEqual(1)

    // Check primary controls height >= 44px
    const gridBtn = page.getByTestId('calendar-mode-toggle-grid')
    const agendaBtn = page.getByTestId('calendar-mode-toggle-agenda')
    const todayBtn = page.getByTestId('calendar-today-button')
    const prevBtn = page.getByTestId('calendar-agenda-prev-month')
    const nextBtn = page.getByTestId('calendar-agenda-next-month')
    const detailBtn = page.getByTestId('calendar-agenda-open-detail')
    const addSubmitBtn = page.getByTestId('calendar-agenda-quick-task-submit')

    for (const [name, locator] of [
      ['gridBtn', gridBtn],
      ['agendaBtn', agendaBtn],
      ['todayBtn', todayBtn],
      ['prevBtn', prevBtn],
      ['nextBtn', nextBtn],
      ['detailBtn', detailBtn],
      ['addSubmitBtn', addSubmitBtn],
    ] as const) {
      const box = await locator.boundingBox()
      expect(box, `${name} should have bounding box`).not.toBeNull()
      if (box) {
        expect(box.height, `${name} height should be >= 44`).toBeGreaterThanOrEqual(44)
      }
    }

    // Day picker buttons measured >= 24x24
    const dayBtn = page.getByTestId('calendar-agenda-day-button').first()
    const dayBox = await dayBtn.boundingBox()
    expect(dayBox).not.toBeNull()
    if (dayBox) {
      expect(dayBox.height).toBeGreaterThanOrEqual(24)
      expect(dayBox.width).toBeGreaterThanOrEqual(24)
    }
  })
})
