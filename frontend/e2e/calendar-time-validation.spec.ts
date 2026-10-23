import { expect, test } from './fixtures/tasks'

const intervalMessage = 'Thời gian kết thúc phải sau thời gian bắt đầu.'

for (const entrypoint of ['list', 'day'] as const) {
  test(`${entrypoint} event editor keeps invalid time draft locally and saves the corrected interval`, async ({ page }) => {
    const day = new Date(Date.now() + 7 * 3_600_000).toISOString().slice(0, 10)
    const source = { id: 'source-manual', name: 'Nguồn kiểm tra giờ', kind: 'manual',
      color: 'rose', is_visible: true, event_count: 1, created_at: null, updated_at: null }
    let event = { id: 'event-time', source_id: source.id, title: 'Buổi kiểm tra giờ',
      starts_at: `${day}T08:00:00+07:00`, ends_at: `${day}T09:00:00+07:00`,
      all_day: false, location: 'Phòng synthetic', description_md: 'Mô tả giữ nguyên',
      created_at: null, updated_at: null }
    const writes: Record<string, unknown>[] = []
    await page.route('**/api/calendar/**', async (route) => {
      const request = route.request()
      const url = new URL(request.url())
      if (url.pathname === '/api/calendar/sources') return route.fulfill({ json: { items: [source] } })
      if (url.pathname === '/api/calendar/annotations') return route.fulfill({ json: { items: [] } })
      if (url.pathname === '/api/calendar/events' && request.method() === 'GET') {
        const from = Date.parse(url.searchParams.get('from')!)
        const to = Date.parse(url.searchParams.get('to')!)
        const items = Date.parse(event.starts_at) < to && Date.parse(event.ends_at) > from ? [event] : []
        return route.fulfill({ json: { items } })
      }
      if (url.pathname === `/api/calendar/events/${event.id}` && request.method() === 'PATCH') {
        const body = request.postDataJSON()
        writes.push(body)
        if (Date.parse(body.ends_at) <= Date.parse(body.starts_at)) {
          return route.fulfill({ status: 422, json: { detail: [{ loc: ['body'],
            msg: 'Value error, ends_at must be after starts_at', type: 'value_error' }] } })
        }
        event = { ...event, ...body }
        return route.fulfill({ json: event })
      }
      return route.fallback()
    })
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch', exact: true }).click()
    if (entrypoint === 'list') {
      await page.getByTestId('calendar-view-toggle-list').click()
      await page.getByRole('button', { name: `Sửa buổi ${event.title}`, exact: true }).click()
    } else {
      await page.locator(`[data-testid="calendar-day-cell"][data-day="${day}"]`).click()
      await page.locator(`[data-testid="calendar-day-event"][data-event-id="${event.id}"]`).click()
    }
    const form = page.getByTestId('calendar-event-form')
    const times = form.locator('input[type="datetime-local"]')
    await form.getByRole('textbox', { name: 'Tiêu đề', exact: true }).fill('Bản nháp giữ nguyên')
    await times.nth(0).fill(`${day}T09:30`)
    await times.nth(1).fill(`${day}T09:30`)
    await form.getByRole('button', { name: 'Lưu buổi', exact: true }).click()
    const error = form.getByTestId('calendar-event-interval-error')
    await expect(error).toHaveText(intervalMessage)
    await expect(times.nth(1)).toBeFocused()
    await expect(times.nth(1)).toHaveAttribute('aria-invalid', 'true')
    await expect(times.nth(1)).toHaveAttribute('aria-describedby', await error.getAttribute('id') as string)
    await expect(times.nth(0)).toHaveValue(`${day}T09:30`)
    await expect(times.nth(1)).toHaveValue(`${day}T09:30`)
    await expect(form.getByRole('textbox', { name: 'Tiêu đề', exact: true })).toHaveValue('Bản nháp giữ nguyên')
    await expect(form.getByRole('textbox', { name: 'Địa điểm', exact: true })).toHaveValue('Phòng synthetic')
    await expect(form.getByRole('textbox', { name: 'Mô tả', exact: true })).toHaveValue('Mô tả giữ nguyên')
    expect(writes).toHaveLength(0)
    await times.nth(1).fill(`${day}T09:00`)
    await expect(error).toHaveText(intervalMessage)
    await form.getByRole('button', { name: 'Lưu buổi', exact: true }).click()
    expect(writes).toHaveLength(0)
    await times.nth(1).fill(`${day}T10:30`)
    await expect(error).toHaveCount(0)
    await form.getByRole('button', { name: 'Lưu buổi', exact: true }).click()
    await expect(form).toBeHidden()
    expect(writes).toHaveLength(1)
    expect(writes[0]).toMatchObject({ title: 'Bản nháp giữ nguyên',
      starts_at: `${day}T09:30:00+07:00`, ends_at: `${day}T10:30:00+07:00`,
      location: 'Phòng synthetic', description_md: 'Mô tả giữ nguyên' })
    expect(writes[0]).not.toHaveProperty('source_id')
  })
}
