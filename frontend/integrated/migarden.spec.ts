import { expect, test, type Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const baseURL = process.env.N01_BROWSER_ORIGIN ?? 'http://127.0.0.1:8871'
const deviceID = 'qa-controller-a'
// This fixture never renders or persists under the app or PWA. Never trace bearer requests.
const fixtureMarker = 'N01_QA_ARTIFACT_CANARY'

async function login(page: Page) {
  const cookieFile = process.env.N01_BROWSER_COOKIE_FILE
  if (cookieFile) {
    const value = (await readFile(resolve(cookieFile), 'utf8')).trim()
    await page.context().addCookies([{ name: 'ms_session', value, url: baseURL, httpOnly: true }])
    await page.goto('/')
  } else {
    await page.goto('/auth/dev-session')
  }
  await expect(page.getByTestId('app-menu-open')).toBeVisible()
  await page.getByTestId('app-menu-open').click()
  await page.getByTestId('migarden-open').click()
  await expect(page).toHaveURL(baseURL + '/migarden')
}

test('N01 browser: saved/applied, all schedule editors, remote START/STOP, chart and history', async ({ browser }, testInfo) => {
  const tokenFile = process.env.N01_DEVICE_TOKEN_FILE
  if (!tokenFile) throw new Error('Provide a fresh QA-only N01_DEVICE_TOKEN_FILE')
  const token = (await readFile(resolve(tokenFile), 'utf8')).trim()
  const mobile = await browser.newContext({
    viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, serviceWorkers: 'block',
  })
  const desktop = await browser.newContext({ viewport: { width: 1280, height: 800 }, serviceWorkers: 'block' })
  const boot = 'browser-' + randomUUID()
  let seq = 0
  let ref: string | null = null
  const stamp = () => new Date().toISOString()
  function event(kind: string, payload: object, other: object = {}) {
    return {
      zone_id: 'zone-a', binding_ref: 'zone-a-v1', boot_id: boot, kind, payload,
      event_id: randomUUID(), sequence: ++seq, config_ref: ref, occurred_at: stamp(), time_quality: 'synced', ...other,
    }
  }
  async function exchange(reports: object[] = [], changes: object = {}, epoch = 0) {
    const response = await fetch(baseURL + '/api/migarden/device/exchange', {
      method: 'POST', headers: { 'content-type': 'application/json', authorization: 'Bearer ' + token },
      body: JSON.stringify({
        protocol: 'migarden.zone-a.v1', device_id: deviceID, boot_id: boot, control_epoch: epoch, reports,
        snapshot: {
          observed_at: stamp(), applied_config_ref: ref, time_quality: 'synced', output: 'off',
          active_session: null, ready: Boolean(ref), blocked_reason: null, ...changes,
        },
      }),
    })
    if (response.status !== 200) throw new Error('Synthetic Controller exchange failed, status ' + response.status)
    return response.json()
  }
  try {
    const page = await mobile.newPage()
    await login(page)
    await expect(page.getByRole('tablist', { name: 'Chọn nội dung' }).getByRole('tab')).toHaveCount(5)
    await expect(page.getByRole('button', { name: 'Tưới ngay' })).toBeDisabled()
    await page.getByRole('button', { name: 'Cấu hình', exact: true }).click()
    await expect(page.getByText('Chưa lưu cấu hình')).toBeVisible()
    await expect(page.getByRole('checkbox', { name: 'Bật lịch' })).not.toBeChecked()
    await expect(page.getByLabel('Thời lượng nút START')).toHaveValue('15')
    await expect(page.getByLabel('Tối đa mỗi lượt')).toHaveValue('30')
    await expect(page.getByLabel('Tổng tối đa')).toHaveValue('120')
    const selectPattern = async (label: string) => {
      await page.getByRole('combobox', { name: 'Lặp lại' }).click()
      await page.getByRole('option', { name: label, exact: true }).click()
    }
    await selectPattern('Một lần')
    await expect(page.getByLabel('Ngày và giờ tưới')).toBeVisible()
    await selectPattern('Theo chu kỳ')
    await expect(page.getByLabel('Mốc đầu chu kỳ')).toBeVisible()
    await selectPattern('Theo thứ')
    await page.getByRole('checkbox', { name: 'Bật lịch' }).click()
    await page.getByRole('button', { name: 'Lưu cấu hình' }).click()
    await expect(page.getByRole('alert')).toContainText('Chọn ít nhất một thứ')
    await page.getByRole('button', { name: 'T2', exact: true }).click()
    await page.getByRole('button', { name: 'T4', exact: true }).click()
    await page.getByRole('button', { name: 'Lưu cấu hình' }).click()
    await expect(page.getByText('Đã lưu · Chờ ESP32 áp dụng')).toBeVisible()
    let response = await exchange()
    expect(response.desired_config.schedule.recurrence).toMatchObject({ kind: 'weekly', days_of_week: [1, 3] })
    ref = response.desired_config.config_ref
    await exchange([event('config_applied', {})])
    await page.getByRole('button', { name: 'Cập nhật' }).click()
    await expect(page.getByText('ESP32 đã xác nhận áp dụng')).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath('Cau-hinh-mobile.png'), fullPage: true })

    const wide = await desktop.newPage()
    await login(wide)
    await expect(wide.getByRole('heading', { name: 'Lượt sắp tới' })).toBeVisible()
    await expect(wide.getByText('Dự kiến theo lịch đã áp dụng.', { exact: false })).toBeVisible()
    await wide.getByRole('button', { name: 'Tưới ngay' }).click()
    await wide.getByLabel('Thời lượng tưới (phút)').fill('0.75')
    await wide.getByRole('button', { name: 'Xem trước' }).click()
    await expect(wide.getByRole('heading', { name: 'Xác nhận tưới Khu A' })).toBeVisible()
    expect((await exchange()).candidates).toEqual([])
    await wide.getByRole('button', { name: 'Xác nhận tưới', exact: true }).click()
    await expect(wide.getByTestId('garden-now')).toContainText('Chờ Controller nhận')
    response = await exchange()
    const start = response.candidates[0]
    expect(start.duration_seconds).toBe(45)
    response = await exchange([event('request_received', {}, { request_id: start.request_id, trigger_source: 'remote' })])
    expect(response.grants[0].request_id).toBe(start.request_id)

    const sessionID = randomUUID()
    const startStamp = stamp()
    const active = {
      session_id: sessionID, request_id: start.request_id, trigger_source: 'remote',
      config_ref: ref, duration_seconds: 45, elapsed_seconds: 0, started_at: startStamp,
    }
    await exchange([event('session_started', { started_at: startStamp, duration_seconds: 45 }, {
      request_id: start.request_id, session_id: sessionID, trigger_source: 'remote',
    })], { output: 'on', active_session: active })
    await wide.getByRole('button', { name: 'Cập nhật' }).click()
    await expect(wide.getByTestId('garden-now')).toContainText('Đang tưới')
    await expect(wide.getByTestId('garden-recent')).toContainText('Có báo cáo đã bắt đầu')
    await expect(wide.getByTestId('garden-recent')).not.toContainText('Chờ Controller nhận')
    const elapsed = await wide.getByTestId('garden-elapsed').innerText()
    await expect(wide.getByTestId('garden-elapsed')).not.toHaveText(elapsed)
    await wide.screenshot({ path: testInfo.outputPath('Tong-quan-desktop.png'), fullPage: true })
    await desktop.setOffline(true)
    await expect(wide.getByTestId('garden-now')).toContainText('Lần cuối xác nhận')
    await expect(wide.getByRole('button', { name: 'Tưới ngay' })).toBeDisabled()
    await desktop.setOffline(false)

    await wide.getByRole('button', { name: 'Dừng tưới' }).click()
    await expect(wide.getByTestId('garden-now')).toContainText('Đã gửi yêu cầu Dừng')
    response = await exchange([], { output: 'on', active_session: active })
    const stop = response.stops[0]
    const endStamp = stamp()
    const elapsedSeconds = Math.round((Date.parse(endStamp) - Date.parse(startStamp)) / 1000)
    await exchange([
      event('stop_processed', { outcome: 'close_requested' }, { request_id: stop.request_id, trigger_source: 'remote' }),
      event('session_ended', {
        started_at: startStamp, ended_at: endStamp, output_duration_seconds: elapsedSeconds,
        outcome: 'stopped', reason: 'remote_stop',
      }, { request_id: start.request_id, session_id: sessionID, trigger_source: 'remote' }),
      event('occurrence_decided', { occurrence_id: randomUUID(), scheduled_at: '2026-11-17T00:00:00Z',
        disposition: 'skipped', reason: 'budget' }, { trigger_source: 'schedule' }),
    ], {}, 1)
    await wide.getByRole('button', { name: 'Cập nhật' }).click()
    await expect(wide.getByTestId('garden-now')).toContainText('Controller đã xử lý Dừng')
    await wide.getByRole('button', { name: '30 ngày', exact: true }).click()
    await expect(wide.getByLabel('Biểu đồ 30 ngày theo giờ Hà Nội')).toBeVisible()
    await wide.getByRole('button', { name: 'Xem số liệu theo ngày' }).click()
    await expect(wide.getByTestId('migarden-chart')).toContainText('Từ web: ' + elapsedSeconds + ' giây')
    await wide.getByRole('button', { name: 'Xem lịch sử' }).click()
    await expect(wide.getByRole('heading', { name: 'Lịch sử Khu A' })).toBeVisible()
    await wide.getByRole('combobox', { name: 'Nguồn' }).click()
    await wide.getByRole('option', { name: 'Theo lịch', exact: true }).click()
    await expect(wide.getByText('Bỏ qua cơ hội lịch')).toBeVisible()
    await expect(wide.getByTestId('garden-history')).not.toContainText(fixtureMarker)
    await wide.goBack()
    await expect(wide.getByRole('heading', { name: 'Lượt sắp tới' })).toBeVisible()
    await page.getByRole('button', { name: 'Tổng quan', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Phút tưới theo ngày' })).toBeVisible()
    expect(await page.evaluate(() => ({ viewport: innerWidth, scroll: document.documentElement.scrollWidth }))).toEqual({ viewport: 390, scroll: 390 })
    await page.screenshot({ path: testInfo.outputPath('Tong-quan-mobile.png'), fullPage: true })
  } finally {
    for (const context of [mobile, desktop]) {
      await context.request.post(baseURL + '/auth/logout').catch(() => {})
      await context.close()
    }
  }
})
