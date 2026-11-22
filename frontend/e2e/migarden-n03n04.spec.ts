import { expect, test, type Page, type Route } from '@playwright/test'

async function fixture(page: Page, confirmed = false) {
  const stamp = () => new Date().toISOString()
  const old = { config_ref: 'synthetic-old-on', zone_id: 'zone-a', binding_ref: 'zone-a-v1', policy: { manual_duration_seconds: 900, max_session_seconds: 1800, max_window_seconds: 7200, window_seconds: 10800 }, schedule: { enabled: true, effective_from: '2026-11-01T00:00:00Z', effective_until: null, duration_seconds: 60, recurrence: { kind: 'daily', at_local_time: '17:20' } } }
  const saved = { ...old, config_ref: 'synthetic-new-off', schedule: { ...old.schedule, enabled: false } }
  const paused = { status: 'paused', config_ref: saved.config_ref, next_at: null, day: null, duration_seconds: null, day_total_seconds: null }
  const on = { status: 'scheduled', config_ref: old.config_ref, next_at: '2099-11-22T10:20:00Z', day: '2099-11-22', duration_seconds: 60, day_total_seconds: 60 }
  const projection = { saved: paused, last_confirmed: confirmed ? paused : on, application_status: confirmed ? 'applied' : 'pending', possible_previous_run: !confirmed }
  const config = () => ({ desired: saved, applied: confirmed ? saved : old, desired_saved_at: stamp(), applied_confirmed_at: stamp(), application_status: projection.application_status, reason: null, schedule_projection: projection })
  const calls: string[] = []
  let hold = false
  let pending: Route | undefined
  const state = () => ({ zone_id: 'zone-a', binding_ref: 'zone-a-v1', server_time: stamp(), connection: 'fresh', last_seen_at: stamp(), snapshot_received_at: stamp(), snapshot: { observed_at: stamp(), time_quality: 'synced', output: 'off', active_session: null, applied_config_ref: confirmed ? saved.config_ref : old.config_ref, ready: true, blocked_reason: null }, config: config(), start_block_reason: confirmed ? null : 'config_not_applied', stop_available: true, start_request: null, stop_request: null, next_schedule: confirmed ? paused : on, health: null })
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname
    calls.push(path + url.search)
    if (path === '/api/me') return route.fulfill({ json: { email: 'synthetic@example.test', signed_in_at: stamp(), expires_at: '2099-01-01T00:00:00Z', private_until: null, private_locked_until: null, pin_is_set: true, pin_is_bootstrap: false, mimi_available: true, migarden_available: true } })
    if (path === '/api/migarden/state') { if (hold) { pending = route; return }; return route.fulfill({ json: state() }) }
    if (path === '/api/migarden/daily') return route.fulfill({ json: { days: [], forecast: on, schedule_projection: projection } })
    if (path === '/api/migarden/history') return route.fulfill({ json: { items: [{ id: 'v:synthetic-new-off', kind: 'schedule_paused', source: null, result: null, reason: null, occurred_at: stamp(), received_at: null, time_quality: 'server', config_ref: saved.config_ref, config_known: true, session_id: null, request_id: null, duration_seconds: null, planned_duration_seconds: null, scheduled_at: null, started_at: null, ended_at: null, evidence: [] }], next_cursor: null, coverage: 'partial', totals: null } })
    if (path === '/api/migarden/config/versions') return route.fulfill({ json: { items: [{ config_ref: saved.config_ref, saved_at: stamp(), bundle: saved, is_saved: true }, { config_ref: old.config_ref, saved_at: '2026-11-21T10:00:00Z', bundle: old, is_last_confirmed: true }], next_cursor: null } })
    if (path.startsWith('/api/migarden/config/versions/')) {
      const ref = decodeURIComponent(path.split('/').at(-1)!)
      return route.fulfill({ json: { config_ref: ref, saved_at: stamp(), bundle: ref === saved.config_ref ? saved : old, previous_ref: ref === saved.config_ref ? old.config_ref : null, previous_bundle: ref === saved.config_ref ? old : null, schedule_changed: true, last_confirmed_ref: old.config_ref, evidence: [] } })
    }
    if (path === '/api/migarden/health') return route.fulfill({ json: { items: [], boots: [], next_cursor: null } })
    if (path === '/api/readyz') return route.fulfill({ json: { status: 'ok', db: 'up', outbox_protocols: [1] } })
    return route.fulfill({ json: { items: [], next_cursor: null } })
  })
  return { calls, hold: () => { hold = true }, release: async () => { hold = false; await pending?.fulfill({ json: state() }); pending = undefined } }
}

test('N04 A opens exact immutable version, seven days, OFF pending and unchanged five shortcuts', async ({ page }, info) => {
  const cell = await fixture(page)
  await page.goto('/migarden')
  await expect(page.getByTestId('garden-health')).toContainText('Chưa có dữ liệu sức khỏe')
  await expect(page.getByTestId('garden-next-schedule').getByText('Đã lưu tạm dừng · Chờ ESP xác nhận', { exact: true })).toBeVisible()
  await expect(page.getByText(/Có thể vẫn tưới/)).toBeVisible()
  await page.getByRole('button', { name: 'Cấu hình', exact: true }).click()
  await page.getByRole('button', { name: 'Xem bản đã lưu', exact: true }).click()
  await expect(page).toHaveURL(/tab=history&version=synthetic-new-off/)
  const versions = page.getByTestId('garden-versions')
  await expect(versions.getByRole('heading', { name: 'Bản synthetic-new-off', exact: true })).toBeVisible()
  await expect(versions).toContainText('Chưa có báo cáo áp dụng/từ chối')
  const history = cell.calls.find(call => call.includes('/history?view=sessions'))!
  const params = new URL('http://synthetic.test' + history).searchParams
  expect((Date.parse(params.get('to_day')!) - Date.parse(params.get('from_day')!)) / 86_400_000).toBe(6)
  expect(params.get('category')).toBe('all')
  const shortcuts = page.getByRole('tablist', { name: 'Chọn nội dung' })
  await expect(shortcuts.getByRole('tab')).toHaveCount(info.project.name === 'mobile' ? 5 : 6)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: `C:/Users/os/Desktop/ai_eng_path/migarden/.local/evidence/n04/2026-nov-22/build-lead/n04-history-${info.project.name}.png`, fullPage: true })
})

test('N03 visible idle quiets all read timers, closed Mimi list stays quiet, restore revalidates before START', async ({ page }) => {
  await page.clock.install()
  const cell = await fixture(page, true)
  await page.goto('/migarden')
  await expect(page.getByRole('button', { name: 'Tưới ngay', exact: true })).toBeEnabled()
  await page.clock.fastForward(301_000)
  await page.waitForTimeout(20)
  const settled = cell.calls.length
  await page.clock.fastForward(350_000)
  await page.waitForTimeout(20)
  expect(cell.calls.length).toBe(settled)
  expect(cell.calls.filter(call => call.includes('/mimi/conversations'))).toHaveLength(0)
  cell.hold()
  await page.getByRole('heading', { name: 'miGarden', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Tưới ngay', exact: true })).toBeDisabled()
  await expect.poll(() => cell.calls.length).toBeGreaterThan(settled)
  await cell.release()
  await expect(page.getByRole('button', { name: 'Tưới ngay', exact: true })).toBeEnabled()
})
