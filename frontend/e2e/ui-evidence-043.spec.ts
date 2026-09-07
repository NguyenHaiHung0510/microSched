import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { test, expect } from './fixtures/tracker'
import { fixturePrivatePin } from './fixtures/tasks'

/** Opt-in real full-app captures. Only synthetic in-memory API data is used. */
test('Task043 synthetic screen evidence with verified private states', async ({ page, taskApi, trackerApi }, testInfo) => {
  test.skip(process.env.CAPTURE_UI_043 !== '1', 'T1 captures after integrated checks, not on every CI run')
  const today = new Date(Date.now() + 7 * 3600_000).toISOString().slice(0, 10)
  const day = (offset: number) => new Date(Date.parse(`${today}T12:00:00Z`) + offset * 86400_000).toISOString().slice(0, 10)
  const directory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../output/task-043/screenshots')
  mkdirSync(directory, { recursive: true })
  const gitHead = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()
  const captures: Array<Record<string, unknown>> = []
  const capture = async (label: string) => {
    await page.evaluate(() => document.fonts.ready)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const file = `${testInfo.project.name}-${label}.png`
    const bytes = await page.screenshot({ path: path.join(directory, file), animations: 'disabled' })
    captures.push({
      file, gitHead, capturedAt: new Date().toISOString(), privateBadge: await page.getByTestId('private-badge').innerText(),
      viewport: page.viewportSize(), width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20),
      md5: createHash('md5').update(bytes).digest('hex'), sha256: createHash('sha256').update(bytes).digest('hex'),
    })
    writeFileSync(path.join(directory, `${testInfo.project.name}-manifest.json`), JSON.stringify(captures, null, 2))
  }
  const taskTemplate = taskApi.tasks[0]
  taskApi.tasks = Array.from({ length: 3 }, (_, index) => ({
    ...taskTemplate, id: `evidence-task-${index}`, title: ['Chuẩn bị kế hoạch dự án mô phỏng', 'Rà soát tài liệu thiết kế ứng dụng', 'Ghi chú công việc riêng tư mô phỏng'][index],
    status: 'open', due_precision: 'date', due_on: today, due_at: null, pinned: false, is_private: index === 2,
    items: [],
  }))
  const notes = Array.from({ length: 35 }, (_, index) => ({
    id: `evidence-note-${index}`, title: `${index % 7 === 0 ? 'Riêng tư' : 'Ghi chú'} · kế hoạch học tập và dự án ${index + 1}`,
    body_md: 'Nội dung mô phỏng với tiếng Việt có dấu, ghi lại tiến độ và bước tiếp theo để kiểm tra khả năng đọc.',
    is_private: index % 7 === 0, pinned: index === 0,
    items: index === 0 ? Array.from({ length: 30 }, (_, item) => ({ id: `note-item-${item}`, content: `Bước ${item + 1}: kiểm tra nội dung và bổ sung dẫn chứng mô phỏng cho tài liệu`, is_completed: item % 3 === 0, position: item })) : [],
    created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-06T00:00:00Z',
  }))
  await page.route('**/api/notes**', (route) => route.fulfill({ json: { items: notes.filter((note) => !note.is_private || Boolean(taskApi.privateUntil)) } }))
  await page.route('**/api/subscriptions**', (route) => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/settings**', (route) => route.fulfill({ json: { items: [] } }))
  const events = Array.from({ length: 42 }, (_, index) => ({
    id: `evidence-event-${index}`, source_id: 'synthetic-course',
    title: ['[DỰ ÁN] Thiết kế hệ thống và phân tích yêu cầu', '[HỌC TẬP] Thực hành lập trình ứng dụng', '[THỰC HÀNH] Kiểm thử và đánh giá chất lượng'][index % 3],
    starts_at: `${day(Math.floor(index / 3) - 3)}T${String(8 + index % 3 * 3).padStart(2, '0')}:00:00+07:00`,
    ends_at: `${day(Math.floor(index / 3) - 3)}T${String(10 + index % 3 * 3).padStart(2, '0')}:00:00+07:00`,
    all_day: false, location: 'Phòng thực hành mô phỏng', description_md: null, created_at: null, updated_at: null,
  }))
  await page.route('**/api/calendar/**', (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/sources')) return route.fulfill({ json: { items: [{ id: 'synthetic-course', name: 'Lịch học mô phỏng', kind: 'manual', is_visible: true, color: 'rose', event_count: events.length, created_at: null, updated_at: null }] } })
    if (url.pathname.endsWith('/annotations')) return route.fulfill({ json: { items: taskApi.privateUntil ? [{ id: 'synthetic-annotation', starts_on: today, ends_on: today, label: 'Kế hoạch riêng tư mô phỏng', note_md: null, is_private: true, color: 'mint', created_at: null, updated_at: null }] : [] } })
    const from = Date.parse(url.searchParams.get('from') ?? '')
    const to = Date.parse(url.searchParams.get('to') ?? '')
    return route.fulfill({ json: { items: events.filter((event) => Date.parse(event.starts_at) < to && Date.parse(event.ends_at) > from) } })
  })
  const trackerTemplate = trackerApi.trackers[0]
  trackerApi.trackers = Array.from({ length: 3 }, (_, index) => ({
    ...trackerTemplate, id: `evidence-tracker-${index}`, name: ['Kiểm tra bản sao lưu mô phỏng', 'Ghi nhận thói quen mỗi ngày', 'Nhật ký riêng tư mô phỏng'][index],
    is_private: index === 2, reminder_mode: index === 2 ? 'after_entry' : 'fixed', reminder_interval_days: index === 0 ? 5 : 1,
    reminder_time: '08:00:00', reminder_action: index === 0 ? 'open_tracker' : 'confirm_event',
    next_reminder_at: `${day(index === 0 ? 5 : 1)}T08:00:00+07:00`,
  }))
  await page.goto('/')
  if (testInfo.project.name === 'mobile') {
    const tabTops = await page.getByRole('tab').evaluateAll((tabs) => tabs.map((tab) => tab.getBoundingClientRect().top))
    expect(Math.max(...tabTops) - Math.min(...tabTops)).toBeLessThan(2)
  }
  await expect(page.getByTestId('task-card')).toHaveCount(3)
  await capture('tasks-top')
  await page.getByTestId('task-load-later').scrollIntoViewIfNeeded()
  await capture('tasks-dates')
  await page.getByRole('tab', { name: 'Ghi chú' }).click()
  await page.getByTestId('private-lock-now').click()
  await expect(page.getByTestId('note-card')).toHaveCount(30)
  await expect(page.getByTestId('note-private-badge-card')).toHaveCount(0)
  await capture('notes-locked-30')
  await page.getByTestId('private-unlock-open').click()
  await page.getByTestId('private-pin-input').fill(fixturePrivatePin)
  await page.getByTestId('private-unlock-submit').click()
  await expect(page.getByTestId('note-card')).toHaveCount(35)
  await expect(page.getByTestId('note-private-badge-card')).toHaveCount(5)
  await capture('notes-unlocked-35')
  await page.locator('[data-testid="note-card"][data-note-id="evidence-note-0"]').getByTestId('note-title').click()
  await expect(page.getByTestId('note-detail-dialog')).toBeVisible()
  await capture('note-private-long-checklist')
  await page.keyboard.press('Escape')
  await page.getByRole('tab', { name: 'Theo dõi' }).click()
  await expect(page.getByTestId('tracker-reminder-group')).toHaveCount(2)
  await capture('upcoming-reminders')
  await page.getByRole('tab', { name: 'Lịch' }).click()
  await expect(page.getByTestId('calendar-day-chip-event').first()).toBeAttached()
  await page.getByTestId('calendar-today-button').click()
  await capture('calendar-grid')
  if (testInfo.project.name === 'desktop') {
    await page.getByTestId('calendar-toggle-sidebar').click()
    await capture('calendar-wide')
  }
  await page.getByTestId('calendar-mode-toggle-agenda').click()
  await expect(page.getByTestId('calendar-agenda-event-title')).toHaveCount(3)
  await capture('calendar-picker')
  await page.getByTestId('calendar-agenda-view').scrollIntoViewIfNeeded()
  await capture('calendar-agenda')
  await page.getByTestId('private-lock-now').click()
  await expect(page.getByTestId('private-unlock-open')).toBeVisible()
})
