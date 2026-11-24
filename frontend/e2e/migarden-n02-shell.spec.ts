import { expect, test, type Page, type Route } from '@playwright/test'
import { test as trackerTest } from './fixtures/tracker'

const start = '2026-11-17T16:59:40Z'
const end = '2026-11-17T17:00:40Z'
const ref = 'n02-synthetic-config'
const baseItem = {
  source: 'schedule', result: 'completed', reason: null, occurred_at: end, received_at: end,
  time_quality: 'synced', request_id: null, session_id: 'synthetic-session', config_ref: ref,
  config_known: true, duration_seconds: 60, planned_duration_seconds: 60, scheduled_at: null,
}
const finished = {
  ...baseItem, id: 'h:synthetic-session', kind: 'session', started_at: start, ended_at: end,
  evidence: [
    { ...baseItem, id: 'r:original-start', kind: 'session_started', result: 'started', occurred_at: start },
    { ...baseItem, id: 'r:original-end', kind: 'session_ended', result: 'completed' },
  ],
}
const interrupted = {
  ...finished, id: 'h:synthetic-unknown', session_id: 'synthetic-unknown', source: 'local_button',
  result: 'unknown', duration_seconds: null, ended_at: null, reason: 'REBOOT_INTERRUPTED', evidence: [],
}
const alreadyOff = {
  ...baseItem, id: 'r:synthetic-stop', kind: 'stop_processed', session_id: null,
  source: 'local_button', result: 'already_off', duration_seconds: null, planned_duration_seconds: null,
  started_at: null, ended_at: null, evidence: [],
}

async function fixture(page: Page, options: { enabled?: boolean; guest?: boolean; schedule?: boolean; sessionGate?: Promise<void> } = {}) {
  const { enabled = true, guest = false, schedule = true, sessionGate } = options
  const stamp = () => new Date().toISOString()
  const since = new Date(Date.now() - 86_400_000).toISOString()
  const initial = {
    config_ref: ref, zone_id: 'zone-a', binding_ref: 'zone-a-v1',
    policy: { manual_duration_seconds: 900, max_session_seconds: 1800, max_window_seconds: 7200, window_seconds: 10800 },
    schedule: { enabled: schedule, effective_from: since.slice(0, 16) + ':00Z', effective_until: null,
      duration_seconds: 60, recurrence: { kind: 'daily', at_local_time: '07:00' } },
  }
  let desired = initial
  const config = () => ({
    desired, applied: initial, desired_saved_at: stamp(), applied_confirmed_at: stamp(),
    application_status: desired === initial ? 'applied' : 'pending', reason: null,
  })
  const requested: string[] = []
  let put: Route | undefined
  let puts = 0
  let stateError = false
  let historyError = false
  let empty = false
  await page.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    if (path.startsWith('/api/migarden/')) requested.push(path + url.search)
    if (path === '/api/me') {
      await sessionGate
      if (guest) return route.fulfill({ status: 401, json: { detail: 'Not authenticated' } })
      return route.fulfill({ json: {
        email: 'n02-synthetic@example.test', signed_in_at: stamp(), expires_at: '2099-01-01T00:00:00Z',
        private_until: null, private_locked_until: null, pin_is_set: true, pin_is_bootstrap: false,
        mimi_available: true, migarden_available: enabled,
      } })
    }
    if (path === '/api/migarden/config' && request.method() === 'PUT') { puts++; put = route; return }
    if (path === '/api/migarden/state') {
      if (stateError) return route.fulfill({ status: 503, json: { detail: 'synthetic_state_unavailable' } })
      const last = new Date(Date.now() - 50_000).toISOString()
      return route.fulfill({ json: {
        zone_id: 'zone-a', binding_ref: 'zone-a-v1', server_time: stamp(), connection: 'stale',
        last_seen_at: last, snapshot_received_at: last,
        snapshot: { observed_at: last, time_quality: 'synced', output: 'off', active_session: null, applied_config_ref: ref, ready: false, blocked_reason: null },
        config: config(), start_block_reason: 'device_stale', stop_available: false, start_request: null, stop_request: null,
        next_schedule: { status: schedule ? 'scheduled' : 'paused', config_ref: ref, next_at: schedule ? '2099-02-01T00:00:00Z' : null,
          day: schedule ? '2099-02-01' : null, duration_seconds: schedule ? 60 : null, day_total_seconds: schedule ? 60 : null },
      } })
    }
    if (path === '/api/migarden/history') {
      if (historyError) return route.fulfill({ status: 503, json: { detail: 'synthetic_history_unavailable' } })
      const cursor = url.searchParams.get('cursor'), source = url.searchParams.get('source')
      const timeline = url.searchParams.get('view') === 'sessions'
      const items = cursor ? [finished] : [interrupted, alreadyOff]
      return route.fulfill({ json: timeline ? {
        items: empty ? [] : items.filter(item => !source || item.source === source), coverage: 'partial',
        next_cursor: empty || cursor ? null : 'synthetic-page-two',
        totals: { recorded_seconds: 60, schedule_seconds: 60, remote_seconds: null, local_button_seconds: null },
      } : { items: [finished.evidence[1]], coverage: 'partial', next_cursor: null } })
    }
    if (path === '/api/migarden/daily') return route.fulfill({ json: { days: [], forecast: { status: 'paused' } } })
    if (path === '/api/readyz') return route.fulfill({ json: { status: 'ok', db: 'up', outbox_protocols: [1] } })
    if (path === '/api/mimi/attention/resolve') return route.fulfill({ status: 404, json: {} })
    return route.fulfill({ json: { items: [], next_cursor: null } })
  })
  return {
    requested, get puts() { return puts },
    stateError(value: boolean) { stateError = value }, historyError(value: boolean) { historyError = value },
    clearHistory() { empty = true },
    async finishSave() {
      if (!put) throw new Error('expected a held local fixture request')
      const payload = put.request().postDataJSON()
      desired = { ...initial, schedule: payload.schedule, policy: payload.policy, config_ref: 'n02-synthetic-revised' }
      await put.fulfill({ json: config() })
      put = undefined
    },
  }
}

test('N02 eligible root, responsive shortcuts, General Task, keyboard and native Back retain explicit destinations', async ({ page }, info) => {
  await fixture(page)
  await page.setViewportSize(info.project.name === 'mobile' ? { width: 360, height: 844 } : { width: 1440, height: 900 })
  await page.goto('/')
  await expect(page).toHaveURL(/\/migarden$/)
  const nav = page.getByRole('tablist', { name: 'Chọn nội dung' })
  const mobile = info.project.name === 'mobile'
  await expect(nav.getByRole('tab')).toHaveText(mobile
    ? ['miGarden', 'Ghi chú', 'Lịch', 'Theo dõi', 'Mimi']
    : ['Task', 'miGarden', 'Ghi chú', 'Lịch', 'Theo dõi', 'Mimi'])
  await expect(nav.getByRole('tab', { name: 'miGarden' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('tabpanel', { name: 'miGarden' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(await nav.getByRole('tab').evaluateAll(tabs => tabs.every(tab => tab.getBoundingClientRect().width >= 44))).toBe(true)
  if (mobile) {
    await page.setViewportSize({ width: 390, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.getByTestId('app-menu-open').tap()
  } else await page.getByTestId('app-menu-open').click()
  const menu = page.getByTestId('app-menu')
  for (const label of ['Task', 'miGarden', 'Ghi chú', 'Lịch', 'Theo dõi', 'Mimi'])
    await expect(menu.getByRole('button', { name: label, exact: true })).toBeVisible()
  await menu.getByRole('button', { name: 'Task', exact: true }).click()
  await expect(page).toHaveURL(/\/tasks$/)
  await page.reload()
  await expect(page.getByRole('tabpanel', { name: 'Task' })).toBeVisible()
  await page.getByTestId('app-logo-button').click()
  await expect(page).toHaveURL(/\/migarden$/)
  await page.goBack()
  await expect(page).toHaveURL(/\/tasks$/)
  await page.goForward()
  await expect(page).toHaveURL(/\/migarden$/)
  await nav.getByRole('tab', { name: 'miGarden' }).focus()
  await page.keyboard.press('ArrowRight')
  await expect(nav.getByRole('tab', { name: 'Ghi chú' })).toHaveAttribute('aria-selected', 'true')
  await expect(page).toHaveURL(/\/$/)
  await page.goBack()
  await expect(page).toHaveURL(/\/migarden$/)
})

test('N02 feature off retains Task and public/deep links stay explicit', async ({ page }) => {
  const cell = await fixture(page, { enabled: false, schedule: false })
  await page.goto('/')
  await expect(page.getByRole('tab', { name: 'Task', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('tab', { name: 'miGarden' })).toHaveCount(0)
  await page.getByTestId('app-menu-open').click()
  await expect(page.getByTestId('migarden-placeholder')).toBeDisabled()
  await page.goto('/migarden?history=1')
  await expect(page.getByText('miGarden chưa bật.', { exact: true })).toBeVisible()
  await expect(page.getByTestId('app-live-status')).toHaveCount(0)
  await page.goto('/home?lang=vi')
  await expect(page).toHaveURL(/\/home\?lang=vi$/)
  expect(cell.requested).toHaveLength(0)
})

test('N02 History B reads actual and unknown rows, STOP without a session and one interval total', async ({ page }, info) => {
  const cell = await fixture(page)
  cell.stateError(true)
  await page.goto('/migarden?history=1')
  await expect(page).toHaveURL(/\/migarden\?history=1$/)
  const region = page.getByTestId('garden-history')
  await expect(region).toBeVisible()
  await expect(page.getByRole('button', { name: 'Lịch sử', exact: true })).toHaveAttribute('aria-current', 'page')
  await expect(page.locator('nav[aria-label="Mục trong miGarden"] [aria-current="page"]')).toHaveCount(1)
  await expect(page.getByTestId('app-live-status')).toHaveAttribute('data-state', 'live')
  const layout = region.getByRole(info.project.name === 'mobile' ? 'list' : 'table', { name: 'Lịch sử tưới' })
  await expect(layout.getByText('Chưa rõ thời lượng', { exact: true })).toBeVisible()
  await expect(layout.getByText('Dừng khi đầu ra đã tắt', { exact: true })).toBeVisible()
  await expect(region.getByText('0 giây', { exact: true })).toHaveCount(0)
  await expect(layout).toBeVisible()
  await region.getByRole('button', { name: 'Cũ hơn' }).click()
  await expect(layout.getByText('23:59:40', { exact: true })).toBeVisible()
  await expect(layout.getByText('00:00:40', { exact: true })).toBeVisible()
  await expect(region).toContainText('1 phút đã ghi nhận')
  const opener = info.project.name === 'mobile'
    ? region.getByRole('button', { name: /23:59:40/ }) : region.getByRole('button', { name: 'Chi tiết', exact: true })
  await opener.click()
  const detail = page.getByRole('dialog', { name: 'Chi tiết lượt tưới' })
  await expect(detail.getByText('Bắt đầu tưới', { exact: true })).toBeVisible()
  await expect(detail.getByText('Kết quả lượt tưới', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(opener).toBeFocused()
  await region.getByRole('button', { name: 'Mới hơn' }).click()
  if (info.project.name === 'mobile') await region.getByRole('button', { name: 'Bộ lọc' }).click()
  await region.getByRole('combobox', { name: 'Nguồn' }).click()
  await page.getByRole('option', { name: 'Tại nút', exact: true }).click()
  await expect.poll(() => cell.requested.filter(path => path.includes('source=local_button')).length).toBeGreaterThan(0)
  await page.getByRole('button', { name: 'Cập nhật', exact: true }).click()
  await expect(region.getByRole('combobox', { name: 'Nguồn' })).toContainText('Tại nút')
  cell.historyError(true)
  await page.getByRole('button', { name: 'Cập nhật', exact: true }).click()
  await expect(page.getByTestId('app-live-status')).toHaveAttribute('data-state', 'error')
  await expect(region.getByRole('alert')).toContainText('Không cập nhật được lịch sử')
  cell.historyError(false); cell.clearHistory()
  await region.getByRole('button', { name: 'Thử lại' }).click()
  await expect(region.getByText('Chưa nhận được sự kiện phù hợp.')).toBeVisible()
})

test('N02 Config guarded subtab/topnav/logo, native Back preserves same-page draft and cannot repeat pending PUT', async ({ page }) => {
  const cell = await fixture(page, { schedule: false })
  await page.goto('/tasks')
  await page.getByRole('tab', { name: 'miGarden' }).click()
  await page.getByRole('button', { name: 'Cấu hình', exact: true }).click()
  const time = page.getByLabel('Giờ tưới')
  await time.fill('08:00')
  await page.goBack()
  await expect(page).toHaveURL(/\/migarden$/)
  await page.goForward()
  await expect(time).toHaveValue('08:00')
  const dialog = page.getByTestId('leave-draft-confirm')
  await page.getByRole('button', { name: 'Lịch sử', exact: true }).click()
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Ở lại' }).click()
  await expect(time).toHaveValue('08:00')
  await page.getByTestId('app-logo-button').click()
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Ở lại' }).click()
  await page.getByRole('tab', { name: 'Ghi chú' }).click()
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Ở lại' }).click()
  await page.getByTestId('app-menu-open').click()
  await page.getByTestId('app-menu').getByRole('button', { name: 'Task', exact: true }).click()
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Ở lại' }).click()
  await page.getByRole('button', { name: 'Lưu cấu hình', exact: true }).click()
  await expect.poll(() => cell.puts).toBe(1)
  await page.getByRole('button', { name: 'Lịch sử', exact: true }).click()
  await expect(dialog.getByRole('button', { name: 'Rời bản nháp' })).toBeDisabled()
  await dialog.getByRole('button', { name: 'Ở lại' }).click()
  await page.goBack()
  await page.goBack()
  await expect(page).toHaveURL(/\/tasks$/)
  await page.goForward()
  await page.goForward()
  await expect(page).toHaveURL(/\/migarden\?tab=config$/)
  await expect(time).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Đang lưu…', exact: true })).toBeDisabled()
  expect(cell.puts).toBe(1)
  await cell.finishSave()
  await expect(time).toHaveValue('08:00')
  await expect(time).toBeEnabled()
  await time.fill('09:00')
  await page.getByRole('button', { name: 'Lịch sử', exact: true }).click()
  await dialog.getByRole('button', { name: 'Rời bản nháp' }).click()
  await expect(page).toHaveURL(/\/migarden\?tab=history$/)
  await page.getByRole('button', { name: 'Cấu hình', exact: true }).click()
  await expect(time).toHaveValue('08:00')
})

test('N02 Overview retains History entry and web freshness does not certify stale ESP', async ({ page }) => {
  const cell = await fixture(page)
  await page.goto('/migarden')
  await expect(page.getByTestId('app-live-status')).toHaveText('Web · live and fresh')
  await expect(page.getByTestId('garden-now')).toContainText('Báo cáo quá cũ')
  await expect(page.getByRole('button', { name: 'Tưới ngay' })).toBeDisabled()
  await page.getByTestId('garden-recent').getByRole('button', { name: 'Xem lịch sử' }).click()
  await expect(page).toHaveURL(/\/migarden\?tab=history$/)
  await expect(page.getByTestId('garden-history')).toBeVisible()
  expect(cell.requested.some(path => path.includes('view=sessions'))).toBe(true)
  await page.goBack()
  await expect(page.getByTestId('garden-recent')).toBeVisible()
  cell.stateError(true)
  await page.getByRole('button', { name: 'Cập nhật', exact: true }).click()
  await expect(page.getByTestId('app-live-status')).toHaveAttribute('data-state', 'error')
})

test('N02 logged-out deep link remains return target without mounting miGarden', async ({ page }) => {
  let release!: () => void
  const sessionGate = new Promise<void>(resolve => { release = resolve })
  const cell = await fixture(page, { guest: true, sessionGate })
  await page.goto('/migarden?history=1')
  await expect(page.getByText('Đang kiểm tra phiên đăng nhập…', { exact: true })).toBeVisible()
  await expect(page.getByTestId('app-live-status')).toHaveCount(0)
  release()
  await expect(page.getByTestId('login-link')).toHaveAttribute('href', /return_to=%2Fmigarden%3Fhistory%3D1/)
  await expect(page.getByTestId('migarden-screen')).toHaveCount(0)
  expect(cell.requested).toHaveLength(0)
})

trackerTest('N02 removes both pending banners while retaining the Tracker queue and total guard', async ({ page, context, trackerApi }) => {
  await page.goto('/')
  await page.getByRole('tab', { name: 'Theo dõi', exact: true }).click()
  await page.getByTestId('tracker-tab-report').click()
  await expect(page.getByTestId('tracker-finance-total')).toBeVisible()
  await page.getByTestId('tracker-tab-capture').click()
  const expense = trackerApi.trackers.find(tracker => tracker.kind === 'finance')!
  const card = page.getByTestId('tracker-card').and(page.locator(`[data-tracker-id="${expense.id}"]`))
  await card.getByTestId('tracker-button').click()
  await card.getByTestId('tracker-amount-input').fill('12345')
  await context.setOffline(true)
  await card.getByRole('button', { name: 'Ghi', exact: true }).click()
  const queue = page.getByTestId('outbox-trigger')
  await expect(queue).toBeVisible()
  await page.getByTestId('tracker-tab-report').click()
  await expect(page.getByTestId('tracker-finance-total')).toHaveText('Đang chờ cập nhật')
  await expect(page.getByTestId('derived-pending')).toHaveCount(0)
  await expect(page.getByText(/Biểu đồ\/báo cáo là lần xác nhận cuối/)).toHaveCount(0)
  await queue.click()
  await expect(page.getByTestId('outbox-panel').getByTestId('outbox-row')).toHaveCount(1)
  expect(trackerApi.count('POST', '/api/tracker/entries')).toBe(0)
})
