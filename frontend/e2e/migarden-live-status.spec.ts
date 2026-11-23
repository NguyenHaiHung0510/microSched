import { expect, test, type Page, type Route } from '@playwright/test'
import type { GardenState, HistoryTimeline, VersionDetail } from '../src/features/migarden/api'

const epoch = Date.parse('2026-11-23T00:00:00Z')
const at = (ms = 0) => new Date(epoch + ms).toISOString()
const networkReceipts = new WeakMap<Page, string[]>()
test.afterEach(async ({ page }, info) => {
  const calls = networkReceipts.get(page)
  if (calls) await info.attach('synthetic-requests', { body: JSON.stringify({ total: calls.length, calls }, null, 2), contentType: 'application/json' })
})
async function fixture(page: Page) {
  await page.clock.install({ time: new Date(epoch - 10_000) })
  const config = {
    config_ref: 'synthetic-config', zone_id: 'synthetic-zone', binding_ref: 'synthetic-binding',
    policy: { manual_duration_seconds: 900, max_session_seconds: 1800, max_window_seconds: 7200, window_seconds: 10800 as const },
    schedule: { enabled: false, effective_from: at(-86_400_000), effective_until: null, duration_seconds: 60, recurrence: { kind: 'daily' as const, at_local_time: '07:00' } },
  }
  let state: GardenState = {
    zone_id: config.zone_id, binding_ref: config.binding_ref, server_time: at(), connection: 'fresh',
    last_seen_at: at(), snapshot_received_at: at(),
    snapshot: { observed_at: at(), time_quality: 'synced', output: 'off', active_session: null, applied_config_ref: config.config_ref, ready: true, blocked_reason: null },
    config: { desired: config, applied: config, desired_saved_at: at(-1000), applied_confirmed_at: at(-1000), application_status: 'applied', reason: null },
    start_block_reason: null, stop_available: true, start_request: null, stop_request: null,
    next_schedule: { status: 'paused', config_ref: config.config_ref, next_at: null, day: null, duration_seconds: null, day_total_seconds: null }, health: null,
  }
  const calls: string[] = []
  networkReceipts.set(page, calls)
  let hold = false, error = false, frozenServer = false, signedIn = true, historyHold = false, historyError = false
  const pending: { route: Route; state: GardenState }[] = []
  const historyPending: Route[] = []
  let timeline: HistoryTimeline = { items: [], next_cursor: null, coverage: 'partial', totals: null }
  let detail: VersionDetail = { config_ref: config.config_ref, saved_at: at(-1000), bundle: config, previous_ref: null, previous_bundle: null, schedule_changed: false, last_confirmed_ref: config.config_ref, evidence: [] }
  const currentTime = () => page.evaluate(() => Date.now())
  await page.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    calls.push(request.method() + ' ' + path + url.search)
    if (path === '/api/me') return route.fulfill(signedIn ? { json: { email: 'a228-synthetic@example.test', signed_in_at: at(), expires_at: '2099-01-01T00:00:00Z', private_until: null, private_locked_until: null, pin_is_set: true, pin_is_bootstrap: false, mimi_available: false, migarden_available: true } } : { status: 401, json: { detail: 'Not authenticated' } })
    if (path === '/api/migarden/state') {
      const reply = structuredClone(state)
      if (!frozenServer) reply.server_time = new Date(await currentTime()).toISOString()
      if (hold) { pending.push({ route, state: reply }); return }
      return route.fulfill(error ? { status: 503, json: { detail: 'synthetic_unavailable' } } : { json: reply })
    }
    if (path === '/api/migarden/start/preview') {
      const now = await currentTime()
      return route.fulfill({ json: { preview_id: 'synthetic-preview', duration_seconds: 900, expires_at: new Date(now + 45_000).toISOString(), context: { zone_id: config.zone_id, binding_ref: config.binding_ref, config_ref: config.config_ref, boot_id: 'synthetic-boot', control_epoch: 0 } } })
    }
    if (path === '/api/migarden/start/confirm' || path === '/api/migarden/stop') {
      const stop = path.endsWith('/stop')
      const command = { request_id: stop ? 'synthetic-stop' : 'synthetic-start', kind: stop ? 'stop' as const : 'start' as const, status: 'pending', reason: null, confirmed_at: new Date(await currentTime()).toISOString(), expires_at: at(60_000), duration_seconds: stop ? null : 900, config_ref: config.config_ref }
      state = { ...state, [stop ? 'stop_request' : 'start_request']: command }
      return route.fulfill({ json: command })
    }
    if (path === '/api/migarden/config' && request.method() === 'PUT') {
      const { expected_config_ref: _expected, ...bundle } = request.postDataJSON()
      state = { ...state, config: { ...state.config, desired: { ...config, ...bundle, config_ref: 'synthetic-new-config' }, desired_saved_at: new Date(await currentTime()).toISOString(), application_status: 'pending' } }
      return route.fulfill({ json: state.config })
    }
    if (path === '/api/migarden/daily') return route.fulfill({ json: { days: [], forecast: state.next_schedule } })
    if (path === '/api/migarden/history') {
      if (historyHold) { historyPending.push(route); return }
      return route.fulfill(historyError ? { status: 503, json: { detail: 'synthetic_history_unavailable' } } : { json: timeline })
    }
    if (path === '/api/migarden/config/versions') return route.fulfill({ json: { items: [{ ...detail, is_saved: true, is_last_confirmed: true }], next_cursor: null } })
    if (path.startsWith('/api/migarden/config/versions/')) return route.fulfill({ json: detail })
    if (path === '/api/migarden/health') return route.fulfill({ json: { items: state.health ? [state.health] : [], boots: state.health ? [{ boot_id: state.health.sample.boot_id, first_seen_at: state.health.received_at }] : [], next_cursor: null } })
    if (path === '/api/readyz') return route.fulfill({ json: { status: 'ok', db: 'up', outbox_protocols: [1] } })
    return route.fulfill({ json: { items: [], next_cursor: null } })
  })
  return {
    calls, pending, get state() { return state }, set state(value: GardenState) { state = value },
    count: (path: string) => calls.filter(call => call.startsWith('GET /api/migarden/' + path)).length,
    async report(output: 'on' | 'off' | 'unknown' = 'off') {
      const now = new Date(await currentTime()).toISOString()
      state = { ...state, server_time: now, snapshot_received_at: now, last_seen_at: now, snapshot: { ...state.snapshot!, output, observed_at: now } }
    },
    hold() { hold = true }, error(value = true) { error = value }, freezeServer() { frozenServer = true },
    async release(status = 200) {
      hold = false
      for (const item of pending.splice(0)) await item.route.fulfill(status === 200 ? { json: item.state } : { status, json: { detail: 'synthetic_unavailable' } }).catch(() => undefined)
    },
    evidence() { detail = { ...detail, evidence: [{ event_id: 'synthetic-reject', kind: 'config_rejected', boot_id: 'synthetic-boot', sequence: 2, applied_at: null, occurred_at: null, received_at: at(15_000), time_quality: 'unknown', reason: 'device_stale' }] } },
    timeline(value: HistoryTimeline) { timeline = value },
    holdHistory() { historyHold = true },
    async releaseHistory(fail = false) {
      historyHold = false; historyError = fail
      for (const route of historyPending.splice(0)) await route.fulfill(fail ? { status: 503, json: { detail: 'synthetic_history_unavailable' } } : { json: timeline }).catch(() => undefined)
    },
    signedOut() { signedIn = false },
    signedIn() { signedIn = true },
  }
}
const start = (page: Page) => page.getByRole('button', { name: 'Tưới ngay', exact: true })
const refresh = (page: Page) => page.getByRole('button', { name: 'Cập nhật', exact: true })
const headline = (page: Page) => page.getByTestId('garden-output')
async function open(page: Page, path = '/migarden') {
  await page.goto(path)
  await expect(page.getByTestId('migarden-screen')).toBeVisible()
  if (!path.includes('tab=')) await expect(headline(page)).toBeVisible()
  await page.clock.pauseAt(new Date(epoch))
  await tick(page, 0)
}
async function tick(page: Page, ms: number) { await page.clock.runFor(ms); for (let turn = 0; turn < 3; turn++) { await page.waitForTimeout(20); await page.clock.runFor(1) } }

test('A228 keeps output and receipt through in-flight/error GET; errors still guard controls', async ({ page }) => {
  const cell = await fixture(page)
  await open(page)
  await expect(headline(page)).toHaveText('Đầu ra tắt')
  const receipt = await page.getByTestId('garden-now').locator('time').first().getAttribute('dateTime')
  cell.hold()
  await tick(page, 1000)
  await expect.poll(() => cell.pending.length).toBe(1)
  await expect(headline(page)).toHaveText('Đầu ra tắt')
  await expect(start(page)).toBeEnabled()
  await cell.release(503)
  await tick(page, 0)
  await expect(page.getByText(/Không đọc được trạng thái mới/)).toBeVisible()
  await expect(headline(page)).toHaveText('Đầu ra tắt')
  await expect(start(page)).toBeDisabled()
  await expect(page.getByTestId('garden-now').locator('time').first()).toHaveAttribute('dateTime', receipt!)
})

test('A228 exactly 15s expires locally once without a network wake; START/Preview/Confirm gate and STOP works', async ({ page }) => {
  const cell = await fixture(page)
  await open(page)
  await start(page).click()
  await page.getByRole('button', { name: 'Xem trước', exact: true }).click()
  await tick(page, 0)
  const confirm = page.getByRole('button', { name: 'Xác nhận tưới', exact: true })
  await tick(page, 0)
  await expect(confirm).toBeEnabled()
  cell.freezeServer()
  cell.hold()
  await page.clock.runFor(epoch + 14_999 - await page.evaluate(() => Date.now()))
  await page.waitForTimeout(30)
  await expect(confirm).toBeEnabled()
  const calls = cell.calls.length
  await page.clock.runFor(1)
  await expect(confirm).toBeDisabled()
  await expect(headline(page)).toHaveText('Chưa rõ trạng thái')
  expect(cell.calls.length).toBe(calls)
  await page.clock.runFor(1)
  expect(cell.calls.length).toBe(calls)
  await page.getByRole('button', { name: 'Đổi thời lượng', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Xem trước', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Hủy', exact: true }).click()
  await expect(start(page)).toBeDisabled()
  await expect(page.getByTestId('garden-last-confirmed')).toContainText('Đầu ra tắt')
  await page.getByRole('button', { name: 'Dừng tưới', exact: true }).click()
  await expect.poll(() => cell.calls.filter(call => call === 'POST /api/migarden/stop').length).toBe(1)
  expect(cell.calls.filter(call => call.includes('start/confirm'))).toHaveLength(0)
})

test('A228 repeated snapshots age out; newer same-value receipts renew age without dependent refetch traffic', async ({ page }, info) => {
  const cell = await fixture(page)
  await open(page)
  await expect(start(page)).toBeEnabled()
  await page.getByRole('button', { name: 'Xem 7 ngày sức khỏe', exact: true }).click()
  await tick(page, 0)
  await tick(page, 15_000)
  await expect(headline(page)).toHaveText('Chưa rõ trạng thái')
  const counts = ['daily', 'history', 'config/versions', 'health'].map(path => cell.count(path))
  for (let index = 0; index < 3; index++) {
    await cell.report()
    await tick(page, 1000)
    await expect(headline(page)).toHaveText('Đầu ra tắt')
    await expect(start(page)).toBeEnabled()
  }
  expect(['daily', 'history', 'config/versions', 'health'].map(path => cell.count(path))).toEqual(counts)
  await page.screenshot({ path: info.outputPath('a228-fresh-same-value.png'), fullPage: true })
})

test('A228 actual ON/UNKNOWN preserve the matching last-confirmed line, active elapsed freezes, and no data does not borrow history/health', async ({ page }, info) => {
  const cell = await fixture(page)
  await open(page)
  await cell.report('on')
  const onReceipt = cell.state.snapshot_received_at!
  cell.state = { ...cell.state, start_block_reason: 'busy', snapshot: { ...cell.state.snapshot!, active_session: { session_id: 'synthetic-on', request_id: null, trigger_source: 'schedule', started_at: at(), duration_seconds: 900, elapsed_seconds: 7, config_ref: 'synthetic-config' } } }
  await tick(page, 1000)
  await expect(headline(page)).toHaveText('Đang tưới')
  await expect(start(page)).toBeDisabled()
  await tick(page, 14_000)
  await expect(headline(page)).toHaveText('Chưa rõ trạng thái')
  const elapsed = await page.getByTestId('garden-elapsed').innerText()
  await tick(page, 2000)
  await expect(page.getByTestId('garden-elapsed')).toHaveText(elapsed)
  await cell.report('unknown')
  await tick(page, 1000)
  await expect(headline(page)).toHaveText('Chưa rõ trạng thái')
  await expect(page.getByTestId('garden-last-confirmed')).toContainText('Đầu ra bật')
  await expect(page.getByTestId('garden-last-confirmed').locator('time')).toHaveAttribute('dateTime', onReceipt)
  await page.screenshot({ path: info.outputPath('a228-unknown-last-on.png'), fullPage: true })
  cell.state = { ...cell.state, zone_id: 'synthetic-other-zone', binding_ref: 'synthetic-other-binding', snapshot: null, snapshot_received_at: null, connection: 'waiting' }
  await tick(page, 1000)
  await expect(page.getByTestId('garden-last-confirmed')).toHaveText('Chưa có xác nhận đầu ra')
})

test('A228 deliberate hidden pause preserves report/date and has no TTL read; return revalidates once and still checks actual age', async ({ page }, info) => {
  const cell = await fixture(page)
  await open(page)
  await expect(headline(page)).toHaveText('Đầu ra tắt')
  const receipt = await page.getByTestId('garden-now').locator('time').first().getAttribute('dateTime')
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    window.dispatchEvent(new Event('visibilitychange'))
  })
  await expect(page.getByTestId('app-live-status')).toHaveText('Web · Tạm dừng cập nhật')
  const count = cell.calls.length
  await tick(page, 60_000)
  expect(cell.calls.length).toBe(count)
  await page.screenshot({ path: info.outputPath('a228-paused.png'), fullPage: true })
  await expect(headline(page)).toHaveText('Đầu ra tắt')
  await expect(page.getByTestId('garden-now').locator('time').first()).toHaveAttribute('dateTime', receipt!)
  cell.hold()
  const reads = cell.count('state')
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    window.dispatchEvent(new Event('visibilitychange'))
  })
  await tick(page, 0)
  await expect(headline(page)).toHaveText('Chưa rõ trạng thái')
  await expect(start(page)).toBeDisabled()
  await expect.poll(() => cell.count('state')).toBe(reads + 1)
  await cell.release()
  await tick(page, 0)
  await expect(start(page)).toBeDisabled()
  await cell.report()
  await tick(page, 1000)
  await expect(start(page)).toBeEnabled()
})

test('A228 same-ref evidence follows bounded history reads, not heartbeat receipts; health/boot and forecast changes refresh their dependencies', async ({ page }) => {
  const cell = await fixture(page)
  await open(page, '/migarden?tab=history&version=synthetic-config')
  await expect(page.getByText('Chưa có báo cáo áp dụng/từ chối cho bản này.', { exact: false })).toBeVisible()
  cell.evidence()
  cell.timeline({ items: [{ id: 'synthetic-external-session', kind: 'session', source: 'local_button', result: 'completed', reason: null, occurred_at: at(10_000), received_at: at(10_000), time_quality: 'synced', session_id: 'synthetic-external-session', request_id: null, config_ref: 'synthetic-config', config_known: true, duration_seconds: 60, planned_duration_seconds: 60, scheduled_at: null, started_at: at(-50_000), ended_at: at(10_000), evidence: [] }], coverage: 'partial', next_cursor: null, totals: null })
  const stateCount = cell.count('state')
  await tick(page, 15_000)
  await expect(page.getByTestId('garden-versions')).toContainText('ESP từ chối')
  await expect(page.getByTestId('garden-history')).toContainText('Tại nút')
  expect(cell.count('state')).toBe(stateCount)
  await page.getByRole('button', { name: 'Tổng quan', exact: true }).click()
  await page.getByRole('button', { name: 'Xem 7 ngày sức khỏe', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Lịch sử sức khỏe' })).toBeVisible()
  const healthReads = cell.count('health'), dailyReads = cell.count('daily')
  cell.state = { ...cell.state, health: { sample_id: 'synthetic-health', received_at: at(16_000), sample: { build_id: 'synthetic-build-2', boot_id: 'synthetic-boot-2', sampled_at: at(16_000), time_quality: 'synced', uptime_seconds: 2, reset_reason: 1, free_heap: 180000, minimum_heap: 160000, wifi_phase: 'CONNECTED', sync_status: 'OK', pending_reports: 0, evidence_gaps: 0 } }, next_schedule: { ...cell.state.next_schedule, status: 'scheduled', next_at: '2099-01-01T00:00:00Z', day: '2099-01-01', duration_seconds: 60, day_total_seconds: 60 } }
  await cell.report()
  await tick(page, 1000)
  await expect(page.getByTestId('garden-health')).toContainText('synthetic-build-2')
  await expect.poll(() => cell.count('health')).toBe(healthReads + 1)
  await expect.poll(() => cell.count('daily')).toBe(dailyReads + 1)
  await expect(page.getByRole('region', { name: 'Lịch sử sức khỏe' })).toContainText('Boot syntheti')
})

test('A228 accepted command cancels a delayed old GET and never stamps a fresh snapshot', async ({ page }) => {
  const cell = await fixture(page)
  await open(page)
  cell.hold()
  await tick(page, 1000)
  await expect.poll(() => cell.pending.length).toBe(1)
  await page.getByRole('button', { name: 'Dừng tưới', exact: true }).click()
  await tick(page, 0)
  await expect(page.getByTestId('garden-now')).toContainText('Yêu cầu Dừng')
  await cell.release()
  await tick(page, 0)
  await expect(page.getByTestId('garden-now')).toContainText('Yêu cầu Dừng')
  await expect(page.getByTestId('garden-now').locator('time').first()).toHaveAttribute('dateTime', at())
  await tick(page, 14_000)
  await expect(headline(page)).toHaveText('Chưa rõ trạng thái')
})

test('A228 accepted config survives a delayed GET; dirty draft/conflict guard and background reads stay independent', async ({ page }) => {
  const cell = await fixture(page)
  await open(page, '/migarden?tab=config')
  await page.getByRole('spinbutton', { name: /Thời lượng nút START/ }).fill('10')
  cell.hold()
  await tick(page, 1000)
  await expect.poll(() => cell.pending.length).toBe(1)
  await expect(page.getByRole('button', { name: 'Lưu cấu hình', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Lưu cấu hình', exact: true }).click()
  await tick(page, 0)
  await expect(page.getByRole('button', { name: 'Lưu cấu hình', exact: true })).toBeDisabled()
  await cell.release()
  await tick(page, 0)
  await expect(page.getByRole('spinbutton', { name: /Thời lượng nút START/ })).toHaveValue('10')
  await page.getByRole('spinbutton', { name: /Thời lượng nút START/ }).fill('12')
  cell.state = { ...cell.state, config: { ...cell.state.config, desired: { ...cell.state.config.desired!, config_ref: 'synthetic-external-config' }, desired_saved_at: at(2000) } }
  await tick(page, 1000)
  await expect(page.getByRole('spinbutton', { name: /Thời lượng nút START/ })).toHaveValue('12')
  await expect(page.getByRole('button', { name: 'Lưu cấu hình', exact: true })).toBeDisabled()
  await expect(page.getByRole('alert')).toContainText('Cấu hình đã thay đổi ở nơi khác')
})


test('A228 history keeps matching accepted rows through a slow/error poll and clears them for a new filter identity', async ({ page }) => {
  const cell = await fixture(page)
  const item = { id: 'synthetic-completed', kind: 'session', source: 'schedule' as const, result: 'completed', reason: null, occurred_at: at(-1000), received_at: at(-1000), time_quality: 'synced', session_id: 'synthetic-completed', request_id: null, config_ref: 'synthetic-config', config_known: true, duration_seconds: 60, planned_duration_seconds: 60, scheduled_at: null, started_at: at(-61_000), ended_at: at(-1000), evidence: [] }
  cell.timeline({ items: [item], coverage: 'partial', next_cursor: null, totals: null })
  await open(page, '/migarden?tab=history&version=synthetic-config')
  const history = page.getByTestId('garden-history')
  await expect(history).toContainText('Hoàn tất')
  const initialReads = cell.count('history')
  cell.holdHistory()
  await tick(page, 15_000)
  await expect.poll(() => cell.count('history')).toBeGreaterThan(initialReads)
  await expect(history).toContainText('Hoàn tất')
  await cell.releaseHistory(true)
  await tick(page, 0)
  await expect(history).toContainText('Không cập nhật được lịch sử')
  await expect(history).toContainText('Hoàn tất')
  cell.timeline({ items: [], coverage: 'partial', next_cursor: null, totals: null })
  await cell.releaseHistory()
  const filter = history.getByRole('button', { name: /Bộ lọc/ })
  if (await filter.isVisible()) await filter.click()
  await history.getByLabel('Từ ngày').fill('2026-11-01')
  await tick(page, 0)
  await expect(history).not.toContainText('Hoàn tất')
  await expect(history).toContainText('Chưa nhận được sự kiện phù hợp')
  expect(cell.calls.some(call => call.includes('from_day=2026-11-01'))).toBe(true)
})

test('A228 Preview retains its actual 45s expiry after fresh reports renew only output age', async ({ page }) => {
  const cell = await fixture(page)
  await open(page)
  await start(page).click()
  await page.getByRole('button', { name: 'Xem trước', exact: true }).click()
  await tick(page, 0)
  const confirm = page.getByRole('button', { name: 'Xác nhận tưới', exact: true })
  await expect(confirm).toBeEnabled()
  for (let index = 0; index < 4; index++) { await cell.report(); await tick(page, 10_000) }
  await cell.report()
  await tick(page, 1000)
  await expect(confirm).toBeEnabled()
  await tick(page, 5000)
  await expect(confirm).toBeDisabled()
  await expect(page.getByText('Bản xem trước đã hết hạn. Hãy xem trước lại.')).toBeVisible()
  expect(cell.calls.some(call => call.includes('/start/confirm'))).toBe(false)
})


test('A228 existing auth lifecycle discards the previous session output confirmation before revalidation', async ({ page }) => {
  const cell = await fixture(page)
  await open(page)
  await expect(headline(page)).toHaveText('Đầu ra tắt')
  cell.signedOut()
  await page.evaluate(() => window.dispatchEvent(new Event('microsched:auth-lost')))
  await tick(page, 0)
  await expect(page.getByTestId('migarden-screen')).toHaveCount(0)
  cell.state = { ...cell.state, snapshot: { ...cell.state.snapshot!, output: 'unknown' }, start_block_reason: 'output_unknown' }
  cell.signedIn()
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    window.dispatchEvent(new Event('visibilitychange'))
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    window.dispatchEvent(new Event('visibilitychange'))
  })
  await tick(page, 0)
  await expect(headline(page)).toHaveText('Chưa rõ trạng thái')
  await expect(page.getByTestId('garden-last-confirmed')).toHaveText('Chưa có xác nhận đầu ra')
})
