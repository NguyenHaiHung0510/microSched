import { expect, test } from './fixtures/tasks'

test('manual source and event can be created, viewed, and deleted with confirmation', async ({ page }) => {
  const sources = [
    {
      id: 'source-manual',
      name: 'Nguồn thủ công',
      kind: 'manual',
      color: 'rose',
      is_visible: true,
      event_count: 0,
      created_at: null,
      updated_at: null,
    },
  ]
  const events: Array<Record<string, unknown>> = []
  await page.route('**/api/calendar/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.pathname === '/api/calendar/sources' && request.method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: sources }) })
      return
    }
    if (url.pathname === '/api/calendar/sources' && request.method() === 'POST') {
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(sources[0]) })
      return
    }
    if (url.pathname === '/api/calendar/events' && request.method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: events }) })
      return
    }
    if (url.pathname === '/api/calendar/events' && request.method() === 'POST') {
      const payload = JSON.parse(request.postData() ?? '{}') as Record<string, unknown>
      const created = { id: 'event-manual', ...payload, created_at: null, updated_at: null }
      events.push(created)
      sources[0].event_count = events.length
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(created) })
      return
    }
    const eventMatch = url.pathname.match(/^\/api\/calendar\/events\/([^/]+)$/)
    if (eventMatch && request.method() === 'DELETE') {
      events.splice(0, events.length)
      sources[0].event_count = 0
      await route.fulfill({ status: 204 })
      return
    }
    await route.fallback()
  })

  await page.goto('/')
  await page.getByRole('tab', { name: 'Lịch' }).click()
  await page.getByTestId('calendar-manual-source-button').click()
  await page.getByLabel('Tên nguồn lịch').fill('Nguồn thủ công')
  await page.getByRole('button', { name: 'Tạo nguồn' }).click()
  await expect(page.getByTestId('calendar-source-row').getByText('Nguồn thủ công')).toBeVisible()

  await page.getByRole('button', { name: 'Thêm buổi' }).click()
  await page.getByLabel('Tiêu đề').fill('Buổi thử nghiệm')
  await page.getByRole('button', { name: 'Tạo buổi' }).click()
  await expect(page.getByTestId('calendar-event-card')).toContainText('Buổi thử nghiệm')

  await page.getByRole('button', { name: 'Xoá nguồn Nguồn thủ công' }).click()
  await expect(page.getByText(/1 buổi của nó/)).toBeVisible()
  await page.getByRole('button', { name: 'Huỷ', exact: true }).last().click()
})

test('ICS import shows the inserted count and source deletion count', async ({ page }) => {
  const sources: Array<Record<string, unknown>> = []
  const events: Array<Record<string, unknown>> = []
  await page.route('**/api/calendar/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.pathname === '/api/calendar/sources' && request.method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: sources }) })
      return
    }
    if (url.pathname === '/api/calendar/sources' && request.method() === 'POST') {
      const payload = JSON.parse(request.postData() ?? '{}') as Record<string, unknown>
      const source = {
        id: 'source-ics',
        ...payload,
        is_visible: true,
        event_count: 1,
        created_at: null,
        updated_at: null,
      }
      sources.push(source)
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(source) })
      return
    }
    if (url.pathname.endsWith('/import') && request.method() === 'POST') {
      events.push({ id: 'event-ics', source_id: 'source-ics', title: 'Buổi ICS', starts_at: '2026-08-15T07:00:00+07:00', ends_at: '2026-08-15T08:00:00+07:00', all_day: false, location: null, description_md: null, created_at: null, updated_at: null })
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ parsed: 1, inserted: 1, removed: 0, duplicates: 0, skipped: [] }) })
      return
    }
    if (url.pathname === '/api/calendar/events' && request.method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: events }) })
      return
    }
    await route.fallback()
  })

  await page.goto('/')
  await page.getByRole('tab', { name: 'Lịch' }).click()
  await page.getByRole('button', { name: 'Thêm nguồn lịch' }).click()
  await page.locator('input[type="file"]').setInputFiles({
    name: 'fixture.ics',
    mimeType: 'text/calendar',
    buffer: Buffer.from('BEGIN:VCALENDAR\nEND:VCALENDAR'),
  })
  await page.getByRole('button', { name: 'Tạo nguồn' }).click()
  await expect(page.getByTestId('calendar-import-report')).toContainText('Đã nhập 1 buổi')
  await page.getByRole('button', { name: 'Xoá nguồn fixture' }).click()
  await expect(page.getByText(/1 buổi của nó/)).toBeVisible()
})
