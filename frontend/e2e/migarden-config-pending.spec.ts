import { expect, test, type Locator, type Page, type Route } from '@playwright/test'

type Pattern = 'once' | 'daily' | 'weekly' | 'interval'
type Bundle = {
  policy: { manual_duration_seconds: number; max_session_seconds: number; max_window_seconds: number; window_seconds: number }
  schedule: {
    enabled: boolean; effective_from: string; effective_until: string | null; duration_seconds: number
    recurrence: { kind: Pattern; at?: string; at_local_time?: string; days_of_week?: number[]; anchor_at?: string; interval_minutes?: number }
  }
}

const originalRef = 'config-pending-synthetic-original'
const savedRef = 'config-pending-synthetic-saved'
const patterns = {
  once: { kind: 'once' as const, at: '2026-11-19T00:00:00Z' },
  daily: { kind: 'daily' as const, at_local_time: '07:00' },
  weekly: { kind: 'weekly' as const, at_local_time: '07:00', days_of_week: [1, 3] },
  interval: { kind: 'interval' as const, anchor_at: '2026-11-17T00:00:00Z', interval_minutes: 1440 },
}

async function openConfiguration(page: Page, pattern: Pattern = 'daily') {
  const original = {
    config_ref: originalRef, zone_id: 'zone-a', binding_ref: 'zone-a-v1',
    policy: { manual_duration_seconds: 900, max_session_seconds: 1800, max_window_seconds: 7200, window_seconds: 10800 },
    schedule: {
      enabled: false, effective_from: '2026-11-17T00:00:00Z', effective_until: null,
      duration_seconds: 900, recurrence: patterns[pattern],
    },
  }
  let desired: Bundle & { config_ref: string; zone_id: string; binding_ref: string } = original
  let version = originalRef
  const stamp = () => new Date().toISOString()
  const config = () => ({
    desired, applied: original, desired_saved_at: stamp(), applied_confirmed_at: stamp(),
    application_status: version === originalRef ? 'applied' : 'pending', reason: null,
  })
  const requests: (Bundle & { expected_config_ref: string | null })[] = []
  const pending: Route[] = []
  await page.route('**/api/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/me') return route.fulfill({ json: {
      email: 'config-pending@example.test', signed_in_at: stamp(), expires_at: '2099-01-01T00:00:00Z',
      private_until: null, private_locked_until: null, pin_is_set: true, pin_is_bootstrap: false,
      mimi_available: false, migarden_available: true,
    } })
    if (path === '/api/migarden/config' && request.method() === 'PUT') {
      requests.push(request.postDataJSON())
      pending.push(route)
      return
    }
    if (path === '/api/migarden/state') return route.fulfill({ json: {
      zone_id: 'zone-a', binding_ref: 'zone-a-v1', server_time: stamp(), connection: 'fresh',
      last_seen_at: stamp(), snapshot_received_at: stamp(),
      snapshot: { observed_at: stamp(), time_quality: 'synced', output: 'off', active_session: null,
        applied_config_ref: originalRef, ready: true, blocked_reason: null },
      config: config(), start_block_reason: null, stop_available: true, start_request: null, stop_request: null,
      next_schedule: { status: 'paused', config_ref: originalRef, next_at: null, day: null, duration_seconds: null, day_total_seconds: null },
    } })
    if (path === '/api/readyz') return route.fulfill({ json: { status: 'ok', db: 'up', outbox_protocols: [1] } })
    return route.fulfill({ json: { items: [], next_cursor: null } })
  })
  await page.goto('/migarden?tab=config')
  await expect(page.getByRole('heading', { name: 'Lịch tưới', exact: true })).toBeVisible()
  const editor = page.locator('form').filter({ has: page.getByRole('heading', { name: 'Lịch tưới', exact: true }) })
  return {
    editor, requests,
    async respond(status: number, canonicalMinutes?: number) {
      const route = pending.shift()
      expect(route, 'the save request is held at the actual HTTP boundary').toBeDefined()
      if (status !== 200) return route!.fulfill({ status, json: { detail: status === 409 ? 'config_conflict' : 'synthetic_unavailable' } })
      const bundle = requests[requests.length - 1]
      desired = { ...original, policy: bundle.policy, config_ref: savedRef,
        schedule: { ...bundle.schedule, duration_seconds: (canonicalMinutes ?? bundle.schedule.duration_seconds / 60) * 60 } }
      version = savedRef
      await route!.fulfill({ json: config() })
    },
    drift() { version = 'config-pending-synthetic-external'; desired = { ...original, config_ref: version } },
  }
}

async function clickByPointer(page: Page, target: Locator, mobile: boolean) {
  await target.scrollIntoViewIfNeeded()
  const box = await target.boundingBox()
  expect(box).not.toBeNull()
  const x = box!.x + box!.width / 2
  const y = box!.y + box!.height / 2
  if (mobile) await page.touchscreen.tap(x, y)
  else await page.mouse.click(x, y)
}

for (const pattern of ['once', 'daily', 'weekly', 'interval'] as const) {
  test(`miGarden ${pattern}: pending save locks keyboard/touch editors and admits one PUT`, async ({ page }, testInfo) => {
    const { editor, requests, respond } = await openConfiguration(page, pattern)
    const duration = editor.getByLabel('Thời lượng mỗi lần')
    await duration.fill('10')
    await editor.getByRole('button', { name: 'Lưu cấu hình', exact: true }).click()
    await expect.poll(() => requests.length).toBe(1)

    const controls = editor.locator('input:not([aria-hidden="true"]), button')
    for (const control of await controls.all()) await expect.soft(control).toBeDisabled({ timeout: 150 })
    const recurrence = editor.getByRole('combobox', { name: 'Lặp lại' })
    // Fieldset inheritance alone does not stop Radix's pointer handlers opening a portal.
    await clickByPointer(page, recurrence, testInfo.project.name === 'mobile')
    await expect.soft(page.getByRole('listbox')).toHaveCount(0, { timeout: 150 })
    await page.keyboard.press('Escape')
    await recurrence.press('ArrowDown')
    await page.keyboard.press('Enter')
    await expect.soft(page.getByRole('listbox')).toHaveCount(0, { timeout: 150 })
    await page.keyboard.press('Escape')
    await duration.press('ArrowUp')
    await expect.soft(duration).toHaveValue('10', { timeout: 150 })
    const toggle = editor.getByRole('checkbox', { name: 'Bật lịch' })
    await clickByPointer(page, toggle, testInfo.project.name === 'mobile')
    await toggle.press('Space')
    await expect.soft(toggle).not.toBeChecked({ timeout: 150 })
    if (pattern === 'weekly') {
      const monday = editor.getByRole('button', { name: 'T2', exact: true })
      await clickByPointer(page, monday, testInfo.project.name === 'mobile')
      await expect.soft(monday).toHaveAttribute('aria-pressed', 'true')
    }
    await editor.evaluate(form => {
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    })
    await expect.soft(editor.getByRole('button', { name: 'Đang lưu…', exact: true })).toBeDisabled({ timeout: 150 })
    expect.soft(requests).toHaveLength(1)
    expect(requests[0]).toMatchObject({ expected_config_ref: originalRef, schedule: { enabled: false, duration_seconds: 600 } })
    await respond(200, 11)
    await expect(duration).toHaveValue('11')
    await expect(recurrence).toBeEnabled()
    await expect(page.getByText('Đã lưu tạm dừng · Chờ ESP xác nhận', { exact: true }).first()).toBeVisible()
    await expect(editor.getByRole('button', { name: 'Lưu cấu hình', exact: true })).toBeDisabled()
  })
}

for (const status of [503, 409]) {
  test(`miGarden delayed ${status}: unlocks, retains draft, retries once with unchanged CAS`, async ({ page }) => {
    const { editor, requests, respond } = await openConfiguration(page)
    const time = editor.getByLabel('Giờ tưới')
    await time.fill('08:00')
    await editor.getByRole('button', { name: 'Lưu cấu hình', exact: true }).click()
    await expect.poll(() => requests.length).toBe(1)
    await expect.soft(time).toBeDisabled()
    await respond(status)
    await expect(editor.getByRole('alert')).toBeVisible()
    await expect(time).toBeEnabled()
    await expect(time).toHaveValue('08:00')
    const save = editor.getByRole('button', { name: 'Lưu cấu hình', exact: true })
    await expect(save).toBeEnabled()
    await time.fill('09:00')
    await save.click()
    await expect.poll(() => requests.length).toBe(2)
    expect(requests[1]).toMatchObject({ expected_config_ref: originalRef,
      schedule: { recurrence: { at_local_time: '09:00' } } })
    await expect.soft(time).toBeDisabled()
    await respond(200)
    await expect(time).toHaveValue('09:00')
    await expect(time).toBeEnabled()
    await expect(editor.getByRole('alert')).toHaveCount(0)
  })
}

test('miGarden external config drift retains draft and blocks blind overwrite', async ({ page }) => {
  const { editor, requests, drift } = await openConfiguration(page)
  await editor.getByLabel('Giờ tưới').fill('08:00')
  drift()
  await page.getByRole('button', { name: 'Cập nhật', exact: true }).click()
  await expect(editor.getByRole('alert')).toContainText('Cấu hình đã thay đổi')
  await expect(editor.getByLabel('Giờ tưới')).toHaveValue('08:00')
  await expect(editor.getByRole('button', { name: 'Lưu cấu hình', exact: true })).toBeDisabled()
  expect(requests).toHaveLength(0)
})
