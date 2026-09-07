import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { test, expect } from './fixtures/tracker'
import { fixturePrivatePin } from './fixtures/tasks'

test('Task045 synthetic UI evidence', async ({ page, taskApi, trackerApi }, info) => {
  test.skip(process.env.CAPTURE_UI_045 !== '1', 'Explicit integrated visual capture only')
  const directory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../output/task-045/screenshots')
  mkdirSync(directory, { recursive: true })
  const gitHead = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()
  const captures: object[] = []
  const capture = async (name: string) => {
    await page.evaluate(() => document.fonts.ready)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const file = `${info.project.name}-${name}.png`
    const bytes = await page.screenshot({ path: path.join(directory, file), animations: 'disabled' })
    captures.push({ file, gitHead, capturedAt: new Date().toISOString(), viewport: page.viewportSize(),
      privateBadge: await page.getByTestId('private-badge').innerText(),
      md5: createHash('md5').update(bytes).digest('hex'), sha256: createHash('sha256').update(bytes).digest('hex') })
    writeFileSync(path.join(directory, `${info.project.name}-manifest.json`), JSON.stringify(captures, null, 2))
  }
  const notes = Array.from({ length: 35 }, (_, index) => ({
    id: `qa-note-${index}`, title: `Kế hoạch cải tiến ứng dụng mô phỏng ${index + 1}`,
    body_md: 'Ghi lại việc còn cần làm và kết quả đã hoàn thành để tiếp tục ở buổi sau.',
    is_private: index % 7 === 0, pinned: index === 0,
    created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-07T00:00:00Z',
    items: index === 0 ? Array.from({ length: 38 }, (_, item) => ({
      id: `qa-item-${item}`, content: ['Rà soát nội dung hướng dẫn và bổ sung ví dụ tiếng Việt', 'KIỂM TRA DẤU TIẾNG VIỆT Ế Ữ Ộ Ằ', 'X'.repeat(70), '📚 Ghi lại kết quả kiểm thử'][item % 4] + ` — bước ${item + 1}`,
      is_completed: item % 4 !== 0, position: item,
    })) : [],
  }))
  await page.route('**/api/notes**', (route) => route.fulfill({ json: { items: notes.filter((note) => !note.is_private || Boolean(taskApi.privateUntil)) } }))
  const template = trackerApi.trackers[0]
  trackerApi.trackers = ['Sinh hoạt mô phỏng', 'Học tập mô phỏng', 'Di chuyển mô phỏng'].map((name, index) => ({
    ...template, id: `qa-tracker-${index}`, name, kind: 'finance', input_mode: 'money', reminder_time: null, is_private: false,
  }))
  trackerApi.entries = Array.from({ length: 20 }, (_, index) => ({
    id: `qa-entry-${index}`, tracker_id: `qa-tracker-${index % 3}`, occurred_at: `2026-09-${String(7 - Math.floor(index / 3)).padStart(2, '0')}T08:00:00+07:00`,
    amount: 45000 + index * 12000, list_amount: null, quantity: null, note_md: null,
    created_at: '2026-09-07T00:00:00Z', updated_at: '2026-09-07T00:00:00Z',
  }))
  await page.route('**/api/tracker/dashboard?*', (route) => route.fulfill({ json: {
    period_start: '2026-09-01T00:00:00+07:00', period_end: '2026-09-07T12:00:00+07:00',
    current_period_days: 6, prev_period_days: 6, prev_period_truncated: false, corrupted_entry_count: 0,
    f1_total: 1800000, f2_current: 1800000, f2_previous: 2100000, f5_net: 3200000,
    f3_groups: ['Sinh hoạt', 'Học tập', 'Di chuyển'].map((name, index) => ({ name, total: [900000, 600000, 300000][index], trackers: [{ tracker_id: `qa-tracker-${index}`, name: trackerApi.trackers[index].name, total: [900000, 600000, 300000][index] }] })),
    f4_top: [{ entry_id: 'qa-entry-0', tracker_id: 'qa-tracker-0', tracker_name: trackerApi.trackers[0].name, amount: 480000 }],
    a2_gap: trackerApi.trackers.map((tracker, index) => ({ tracker_id: tracker.id, days_since_last: index === 0 ? 2 : null, avg_interval_days: index === 0 ? 3 : null })),
    a3_counts: { week: 7, month: 12, year: 120 }, a4_trend: { current_month: 12, prev_avg: 15, trend: 'down' },
    f6: { monthly_burn: 250000, subscription_count: 1, upcoming: [], corrupted_subscription_count: 0 },
  } }))
  await page.goto('/')
  await page.getByRole('tab', { name: 'Ghi chú' }).click()
  await page.getByTestId('private-lock-now').click()
  await expect(page.getByTestId('note-card')).toHaveCount(30)
  await capture('notes-locked-30')
  await page.getByTestId('private-unlock-open').click()
  await page.getByTestId('private-pin-input').fill(fixturePrivatePin)
  await page.getByTestId('private-unlock-submit').click()
  await expect(page.getByTestId('note-card')).toHaveCount(35)
  await capture('notes-unlocked-35')
  await page.locator('[data-testid="note-card"][data-note-id="qa-note-0"]').getByTestId('note-title').click()
  await expect(page.getByTestId('note-detail-dialog')).toBeVisible()
  await capture('note-detail-checklist')
  await page.keyboard.press('Escape')
  await page.getByRole('tab', { name: 'Theo dõi' }).click()
  await expect(page.getByTestId('app-live-status')).toHaveAttribute('data-state', 'live')
  await capture('tracker-overview')
  await page.getByTestId('tracker-open-report').click()
  await capture('finance-report')
  await page.getByTestId('tracker-entries-toggle').click()
  await page.getByTestId('tracker-entries-toggle').scrollIntoViewIfNeeded()
  await capture('recent-entries')
  await page.getByTestId('private-lock-now').click()
})
