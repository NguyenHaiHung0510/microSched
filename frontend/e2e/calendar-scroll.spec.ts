import { expect, test } from './fixtures/tasks'

/**
 * 010b §7.7–7.10: grid behavior, mini-nav, measurements, touch-only paths.
 * Calendar data is generated relative to the real current date so the grid's
 * ±6 month window always contains the fixtures.
 */

const VN_OFFSET_MS = 7 * 3_600_000

function vnDay(offsetDays: number): string {
  return new Date(Date.now() + offsetDays * 86_400_000 + VN_OFFSET_MS)
    .toISOString()
    .slice(0, 10)
}

function event(
  id: string,
  sourceId: string,
  start: string,
  end: string,
  extra: Record<string, unknown> = {},
) {
  return {
    id,
    source_id: sourceId,
    title: id,
    starts_at: start,
    ends_at: end,
    all_day: false,
    location: null,
    description_md: null,
    created_at: null,
    updated_at: null,
    ...extra,
  }
}

function iso(day: string, hour: number): string {
  return `${day}T${String(hour).padStart(2, '0')}:00:00+07:00`
}

const sources = [
  {
    id: 'source-manual',
    name: 'Nguồn thủ công',
    kind: 'manual',
    color: 'rose',
    is_visible: true,
    event_count: 3,
    created_at: null,
    updated_at: null,
  },
  {
    id: 'source-ics',
    name: 'Lịch công việc',
    kind: 'ics',
    color: 'sky',
    is_visible: true,
    event_count: 1,
    created_at: null,
    updated_at: null,
  },
]

function jsonResponse(body: unknown, status = 200) {
  return {
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  }
}

function calendarRoutes(
  page: import('@playwright/test').Page,
  state: {
    events: Array<Record<string, unknown>>
    annotations: Array<Record<string, unknown>>
  },
) {
  return page.route('**/api/calendar/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method()
    const path = url.pathname

    if (path === '/api/calendar/sources' && method === 'GET') {
      await route.fulfill(jsonResponse({ items: sources }))
      return
    }
    if (path === '/api/calendar/events' && method === 'GET') {
      const from = url.searchParams.get('from')!
      const to = url.searchParams.get('to')!
      const items = state.events.filter((entry) => {
        const starts = new Date(String(entry.starts_at)).getTime()
        const ends = new Date(String(entry.ends_at)).getTime()
        return starts < Date.parse(to) && ends > Date.parse(from)
      })
      await route.fulfill(jsonResponse({ items }))
      return
    }
    if (path === '/api/calendar/annotations' && method === 'GET') {
      const from = url.searchParams.get('from')!
      const to = url.searchParams.get('to')!
      const items = state.annotations.filter(
        (entry) =>
          String(entry.starts_on) <= to && String(entry.ends_on) >= from,
      )
      await route.fulfill(jsonResponse({ items }))
      return
    }
    if (path === '/api/calendar/annotations' && method === 'POST') {
      const payload = JSON.parse(request.postData() ?? '{}') as Record<string, unknown>
      const created = {
        id: `ann-created-${Date.now()}`,
        ...payload,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }
      state.annotations.push(created)
      await route.fulfill(jsonResponse(created, 201))
      return
    }
    const annotationMatch = path.match(/^\/api\/calendar\/annotations\/([^/]+)$/)
    if (annotationMatch && method === 'PATCH') {
      const payload = JSON.parse(request.postData() ?? '{}') as Record<string, unknown>
      const target = state.annotations.find((entry) => entry.id === annotationMatch[1])
      if (!target) {
        await route.fulfill({ status: 404 })
        return
      }
      Object.assign(target, payload, { updated_at: new Date().toISOString() })
      await route.fulfill(jsonResponse(target))
      return
    }
    if (annotationMatch && method === 'DELETE') {
      state.annotations = state.annotations.filter(
        (entry) => entry.id !== annotationMatch[1],
      )
      await route.fulfill({ status: 204 })
      return
    }
    await route.fallback()
  })
}

test.beforeEach(async ({ page, taskApi }) => {
  // A task due today gives the grid a task chip on today's cell (spec §5.4).
  const dueToday = taskApi.tasks.find((entry) => entry.id === 'task-011')
  if (dueToday) dueToday.due_at = iso(vnDay(0), 10)
})

test.describe('mobile (390x844, touch)', () => {
  test.skip(({ isMobile }) => !isMobile, 'mobile project only')

  test('opens at today week with the page itself not scrolled', async ({ page }) => {
    const state = {
      events: [
        event('event-today', 'source-manual', iso(vnDay(0), 9), iso(vnDay(0), 10)),
      ],
      annotations: [],
    }
    await calendarRoutes(page, state)

    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    const container = page.getByTestId('calendar-scroll-container')
    await expect(container).toBeVisible()

    const result = await page.evaluate(() => ({
      scrollY: window.scrollY,
      containerTop: (
        document.querySelector('[data-testid="calendar-scroll-container"]') as HTMLElement
      ).scrollTop,
    }))
    expect(result.scrollY).toBe(0)
    expect(result.containerTop).toBeGreaterThan(0)

    const todayCell = page.locator(
      `[data-testid="calendar-day-cell"][data-day="${vnDay(0)}"]`,
    )
    await expect(todayCell).toContainText('event-today')
  })

  test('day dialog opens on tap and closes by tapping outside', async ({ page }) => {
    await calendarRoutes(page, { events: [], annotations: [] })
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()

    const todayCell = page.locator(
      `[data-testid="calendar-day-cell"][data-day="${vnDay(0)}"]`,
    )
    await expect(todayCell).toBeVisible()
    await todayCell.tap()
    await expect(page.getByTestId('calendar-day-dialog')).toBeVisible()

    await page.locator('body').tap({ position: { x: 12, y: 12 } })
    await expect(page.getByTestId('calendar-day-dialog')).toBeHidden()
  })

  test('adds a day annotation from the dialog and sees it on the cell', async ({ page }) => {
    const state = { events: [], annotations: [] }
    await calendarRoutes(page, state)
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()

    const todayCell = page.locator(
      `[data-testid="calendar-day-cell"][data-day="${vnDay(0)}"]`,
    )
    await todayCell.tap()
    await page.getByTestId('calendar-day-add-annotation').tap()
    await page.getByLabel('Nhãn').fill('Sinh nhật mẹ')
    await page.getByRole('button', { name: 'Thêm dấu ngày' }).tap()
    await expect(page.getByTestId('calendar-annotation-form')).toBeHidden()

    await page.locator('body').tap({ position: { x: 12, y: 12 } })
    await expect(
      page.locator(
        `[data-testid="calendar-day-cell"][data-day="${vnDay(0)}"] [data-testid="calendar-day-annotation"]`,
      ),
    ).toHaveCount(1)
  })

  test('moves a task from the dialog and undoes it back to the old deadline', async ({
    page,
    taskApi,
  }) => {
    await calendarRoutes(page, { events: [], annotations: [] })
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()

    const moved = taskApi.tasks.find((entry) => entry.id === 'task-004')!
    const originalDue = moved.due_at

    const todayCell = page.locator(
      `[data-testid="calendar-day-cell"][data-day="${vnDay(0)}"]`,
    )
    await todayCell.tap()
    await page.getByTestId('calendar-day-move-task').tap()
    await expect(page.getByText('Dời việc sang ngày này').first()).toBeVisible()
    await page.getByRole('button', { name: /Việc trễ hạn thứ nhất/ }).tap()

    await expect(page.getByRole('button', { name: 'Hoàn tác' })).toBeVisible()
    expect(moved.due_at).toBe(`${vnDay(0)}T23:59:00+07:00`)

    await page.getByRole('button', { name: 'Hoàn tác' }).tap()
    await expect
      .poll(() => moved.due_at)
      .toBe(originalDue)
  })

  test('move picker loads one bounded page only when opened and retains its cursor', async ({
    page,
    taskApi,
  }) => {
    await calendarRoutes(page, { events: [], annotations: [] })
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    await expect(page.getByTestId('calendar-scroll-container')).toBeVisible()
    const before = taskApi.count('GET', '/api/tasks')
    await page.locator(`[data-testid="calendar-day-cell"][data-day="${vnDay(0)}"]`).tap()
    await expect(page.getByTestId('calendar-day-dialog')).toBeVisible()
    expect(taskApi.count('GET', '/api/tasks')).toBe(before)
    await page.getByTestId('calendar-day-move-task').tap()
    await expect(page.getByText('Dời việc sang ngày này').first()).toBeVisible()
    await expect.poll(() => taskApi.count('GET', '/api/tasks')).toBe(before + 1)
    if (await page.getByTestId('calendar-move-load-more').isVisible()) {
      await page.getByTestId('calendar-move-load-more').click()
      await expect.poll(() => taskApi.count('GET', '/api/tasks')).toBe(before + 2)
    }
  })

  test('private lock remounts calendar and closes a detail dialog', async ({ page, taskApi }) => {
    const privateTask = taskApi.tasks.find((entry) => entry.id === 'task-009')!
    privateTask.due_at = iso(vnDay(0), 10)
    await calendarRoutes(page, { events: [], annotations: [] })
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    await page.locator(`[data-testid="calendar-day-cell"][data-day="${vnDay(0)}"]`).tap()
    await expect(page.locator('[data-testid="calendar-day-task"]').filter({ hasText: 'Task riêng tư' })).toBeVisible()
    await page.getByTestId('private-lock-now').evaluate((element) => (element as HTMLButtonElement).click())
    await expect.poll(() => taskApi.count('POST', '/api/private/lock')).toBe(1)
    await expect(page.getByText('Task riêng tư')).toHaveCount(0)
    await expect(page.getByTestId('calendar-day-dialog')).toBeHidden()
  })

  test('mini-nav does not exist on mobile', async ({ page }) => {
    await calendarRoutes(page, { events: [], annotations: [] })
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    await expect(page.getByTestId('calendar-mininav')).toBeHidden()
  })

  test('day cells measure at least 44x44', async ({ page }) => {
    await calendarRoutes(page, { events: [], annotations: [] })
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    const rect = await page
      .getByTestId('calendar-day-cell')
      .first()
      .evaluate((element) => {
        const box = element.getBoundingClientRect()
        return { width: box.width, height: box.height }
      })
    expect(rect.width).toBeGreaterThanOrEqual(44)
    expect(rect.height).toBeGreaterThanOrEqual(44)
  })

  test('event/task/annotation text is at least 12px', async ({ page }) => {
    const state = {
      events: [
        event('event-today', 'source-manual', iso(vnDay(0), 9), iso(vnDay(0), 10)),
      ],
      annotations: [
        {
          id: 'ann-today',
          starts_on: vnDay(0),
          ends_on: vnDay(0),
          label: 'Về quê',
          note_md: null,
          color: 'rose',
          is_private: false,
          created_at: null,
          updated_at: null,
        },
      ],
    }
    await calendarRoutes(page, state)
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()

    for (const testId of [
      'calendar-day-chip-event',
      'calendar-day-chip-task',
      'calendar-day-annotation',
    ]) {
      const fontSize = await page
        .getByTestId(testId)
        .first()
        .evaluate((element) => getComputedStyle(element).fontSize)
      expect(parseFloat(fontSize), `${testId} font`).toBeGreaterThanOrEqual(12)
    }
  })
})

test.describe('desktop (1280x800)', () => {
  test.skip(({ isMobile }) => isMobile, 'desktop project only')

  test('view toggle persists across a reload', async ({ page }) => {
    await calendarRoutes(page, { events: [], annotations: [] })
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    await page.getByTestId('calendar-view-toggle-list').click()
    await expect(page.getByTestId('calendar-view-toggle-list')).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await page.reload()
    await page.getByRole('tab', { name: 'Lịch' }).click()
    await expect(page.getByTestId('calendar-view-toggle-list')).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await expect(page.getByTestId('calendar-manual-source-button')).toBeVisible()
    await page.getByTestId('calendar-view-toggle-grid').click()
    await expect(page.getByTestId('calendar-scroll-container')).toBeVisible()
  })

  test('mini-nav click jumps the main calendar to that week', async ({ page }) => {
    await calendarRoutes(page, { events: [], annotations: [] })
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()

    const header = page.getByTestId('calendar-month-header')
    await expect(header).toBeVisible()
    const before = await header.textContent()

    // Mini-nav luôn hiện đúng hai tháng (spec §5.3): tháng đang xem + tháng kế.
    // Tháng đang xem phụ thuộc vị trí cuộn (tuần biên của tháng trước vẫn có thể
    // nằm trong tập đang giao), nên không hardcode từ hôm nay — lấy ngày cuối của
    // khối thứ hai từ chính DOM. Tuần chứa ngày cuối tháng nằm sâu trong tháng đó,
    // nên tháng header chắc chắn đổi sang nhãn của khối thứ hai.
    const miniNavDays = page.getByTestId('calendar-mininav-day')
    await expect(miniNavDays.first()).toBeVisible()
    const dayCount = await miniNavDays.count()
    const targetDay = await miniNavDays.nth(dayCount - 1).getAttribute('data-day')
    const targetMonth = targetDay!.slice(0, 7)
    await miniNavDays.nth(dayCount - 1).click()

    const expectedLabel = new Intl.DateTimeFormat('vi-VN', {
      month: 'long',
      year: 'numeric',
      timeZone: 'UTC',
    }).format(
      new Date(
        Date.UTC(
          Number(targetMonth.slice(0, 4)),
          Number(targetMonth.slice(5, 7)) - 1,
          1,
        ),
      ),
    )
    await expect(header).toHaveText(expectedLabel, { timeout: 10_000 })
    expect(before).not.toBe(expectedLabel)
  })

  test('scrolling changes the sticky month header', async ({ page }) => {
    await calendarRoutes(page, { events: [], annotations: [] })
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()

    const header = page.getByTestId('calendar-month-header')
    const before = await header.textContent()
    await page
      .getByTestId('calendar-scroll-container')
      .evaluate((element) => (element.scrollTop += 2500))
    await expect
      .poll(async () => header.textContent(), { timeout: 10_000 })
      .not.toBe(before)
  })

  test('extending calendar months changes the bounded task range key and request', async ({
    page,
  }) => {
    const taskUrls: string[] = []
    page.on('request', (request) => {
      const url = new URL(request.url())
      if (request.method() === 'GET' && url.pathname === '/api/tasks') taskUrls.push(url.toString())
    })
    await calendarRoutes(page, { events: [], annotations: [] })
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    await expect(page.getByTestId('calendar-scroll-container')).toBeVisible()
    await expect.poll(() => taskUrls.length).toBeGreaterThan(0)
    const initialRange = new URL(taskUrls[0]).searchParams.get('from') + '|' + new URL(taskUrls[0]).searchParams.get('to')
    const container = page.getByTestId('calendar-scroll-container')
    await container.evaluate((element) => {
      element.scrollTop = element.scrollHeight
      element.dispatchEvent(new Event('scroll', { bubbles: true }))
    })
    await page.waitForTimeout(100)
    await container.evaluate((element) => {
      element.scrollTop = element.scrollHeight
      element.dispatchEvent(new Event('scroll', { bubbles: true }))
    })
    await expect.poll(() => taskUrls.length).toBeGreaterThan(1)
    const ranges = new Set(taskUrls.map((value) => {
      const url = new URL(value)
      return `${url.searchParams.get('from')}|${url.searchParams.get('to')}`
    }))
    expect(ranges.has(initialRange)).toBe(true)
    expect(ranges.size).toBeGreaterThan(1)
    expect(taskUrls.every((value) => !value.includes('offset='))).toBe(true)
  })

  test('overdue task card shows the three reschedule buttons and Hôm nay works', async ({
    page,
    taskApi,
  }) => {
    await calendarRoutes(page, { events: [], annotations: [] })
    await page.goto('/')
    await page.getByRole('tab', { name: 'Task' }).click()

    const card = page.locator('[data-testid="task-card"][data-task-id="task-004"]')
    await expect(card).toBeVisible()
    await expect(card.getByTestId('task-reschedule-today')).toBeVisible()
    await expect(card.getByTestId('task-reschedule-tomorrow')).toBeVisible()
    await expect(card.getByTestId('task-reschedule-day-after')).toBeVisible()

    const moved = taskApi.tasks.find((entry) => entry.id === 'task-004')!
    await card.getByTestId('task-reschedule-today').click()
    await expect(page.getByRole('button', { name: 'Hoàn tác' })).toBeVisible()
    expect(moved.due_at).toBe(`${vnDay(0)}T23:59:00+07:00`)
  })

  test('mini-nav day cells measure at least 24x24', async ({ page }) => {
    await calendarRoutes(page, { events: [], annotations: [] })
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    const rect = await page
      .getByTestId('calendar-mininav-day')
      .first()
      .evaluate((element) => {
        const box = element.getBoundingClientRect()
        return { width: box.width, height: box.height }
      })
    expect(rect.width).toBeGreaterThanOrEqual(24)
    expect(rect.height).toBeGreaterThanOrEqual(24)
  })
})

test('an ICS event opened from the day dialog shows the will-lose-edits warning', async ({
  page,
}) => {
  const state = {
    events: [
      event('event-ics', 'source-ics', iso(vnDay(3), 7), iso(vnDay(3), 8)),
    ],
    annotations: [],
  }
  await calendarRoutes(page, state)
  await page.goto('/')
  await page.getByRole('tab', { name: 'Lịch' }).click()

  const icsCell = page.locator(
    `[data-testid="calendar-day-cell"][data-day="${vnDay(3)}"]`,
  )
  await icsCell.click()
  await page.getByTestId('calendar-day-event').click()
  await expect(page.getByTestId('calendar-event-dialog')).toBeVisible()
  await expect(page.getByText('sửa tay sẽ mất khi nhập lại')).toBeVisible()
})

test('desktop font sizes are at least 12px', async ({ page, taskApi }) => {
  const dueToday = taskApi.tasks.find((entry) => entry.id === 'task-011')
  if (dueToday) dueToday.due_at = iso(vnDay(0), 10)
  const state = {
    events: [
      event('event-today', 'source-manual', iso(vnDay(0), 9), iso(vnDay(0), 10)),
    ],
    annotations: [
      {
        id: 'ann-today',
        starts_on: vnDay(0),
        ends_on: vnDay(0),
        label: 'Về quê',
        note_md: null,
        color: 'rose',
        is_private: false,
        created_at: null,
        updated_at: null,
      },
    ],
  }
  await calendarRoutes(page, state)
  await page.goto('/')
  await page.getByRole('tab', { name: 'Lịch' }).click()

  for (const testId of [
    'calendar-day-chip-event',
    'calendar-day-chip-task',
    'calendar-day-annotation',
  ]) {
    const fontSize = await page
      .getByTestId(testId)
      .first()
      .evaluate((element) => getComputedStyle(element).fontSize)
    expect(parseFloat(fontSize), `${testId} font`).toBeGreaterThanOrEqual(12)
  }
})
