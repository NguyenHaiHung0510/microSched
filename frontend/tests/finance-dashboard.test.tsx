import assert from 'node:assert/strict'
import { expect, test } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import { DashboardPanel } from '../src/DashboardPanel'
import { financeBarScale, financePeriodLabels, financeShares } from '../src/finance-chart'
import { activityCountByTrackerDay, daysInReportMonth, reportMonthOffset } from '../src/tracker-rhythm'
import type { DashboardResponse, Tracker } from '../src/tracker-ui'

const dashboard: DashboardResponse = {
  period_start: '2026-09-01T00:00:00+07:00',
  period_end: '2026-09-07T12:30:00+07:00',
  current_period_days: 6,
  prev_period_days: 6,
  prev_period_truncated: false,
  corrupted_entry_count: 0,
  f1_total: 300_000,
  f2_current: 300_000,
  f2_previous: 400_000,
  report_months: 1,
  previous_period_start: '2026-08-01T00:00:00+07:00',
  previous_period_end: '2026-09-01T00:00:00+07:00',
  finance_months: [{ month: '2026-09', period_start: '2026-09-01T00:00:00+07:00', period_end: '2026-09-07T12:30:00+07:00', total: 300_000 }],
  activity_month: '2026-09',
  activity_days: [{ tracker_id: 'food', day: '2026-09-02', count: 2 }],
  f3_groups: [{ name: 'Sinh hoạt', total: 300_000, trackers: [{ tracker_id: 'food', name: '', total: 300_000 }] }],
  f4_top: [],
  f5_net: -100_000,
  a2_gap: [
    { tracker_id: 'food', current_days: 2, avg_days: 3, enough: true },
    { tracker_id: 'walk', current_days: null, avg_days: null, enough: false },
    { tracker_id: 'read', current_days: null, avg_days: null, enough: false },
  ],
  a3_counts: { week: 2, month: 3, year: 4 },
  a4_trend: { current_month: 3, prev_avg: 2, trend: 'up' },
  f6: { monthly_burn: 0, subscription_count: 0, upcoming: [], corrupted_subscription_count: 0 },
}
const trackers = [
  { id: 'food', name: 'Ăn uống' },
  { id: 'walk', name: 'Đi bộ' },
  { id: 'read', name: 'Đọc sách' },
] as Tracker[]
const render = (data: DashboardResponse | null = dashboard, error: unknown = null) => renderToStaticMarkup(
  <DashboardPanel dashboard={data} monthLabel="09/2026" trackers={trackers} loading={false} error={error} onRetry={() => undefined} />,
)

test('net balance is signed and positive green, negative red, zero neutral', () => {
  for (const [amount, color, text] of [
    [825_000, 'text-ok', '+825.000 ₫'],
    [-135_000, 'text-bad', '-135.000 ₫'],
    [0, 'text-foreground', '0 ₫'],
  ] as const) {
    const html = render({ ...dashboard, f5_net: amount })
    const net = html.match(/<dd data-testid="dashboard-f5-net" class="([^"]+)">([\s\S]*?)<\/dd>/)
    assert.ok(net)
    assert.ok(net[1].split(' ').includes(color))
    assert.equal(net[2].trim(), text)
  }
})

test('finance bars share a real zero baseline and do not turn zero into visible money', () => {
  const positive = financeBarScale([0, 100, 400])
  assert.deepEqual(positive.bar(0), { left: 0, width: 0 })
  assert.deepEqual(positive.bar(100), { left: 0, width: 25 })
  assert.deepEqual(positive.bar(400), { left: 0, width: 100 })
  const signed = financeBarScale([-100, 300])
  assert.equal(signed.zero, 25)
  assert.deepEqual(signed.bar(-100), { left: 0, width: 25 })
  assert.deepEqual(signed.bar(300), { left: 25, width: 75 })
  assert.deepEqual(financeBarScale([0, 0]).bar(0), { left: 0, width: 0 })
  assert.deepEqual(financeBarScale([100, NaN]).bar(NaN), { left: 0, width: 0 })
})

test('composition percentages require a positive whole with no negative or missing parts', () => {
  assert.deepEqual(financeShares([300, 100, 0]), [75, 25, 0])
  assert.equal(financeShares([0, 0]), null)
  assert.equal(financeShares([300, -100]), null)
  assert.equal(financeShares([300, NaN]), null)
})

test('period labels use absolute backend windows rather than elapsed-day reconstruction', () => {
  assert.deepEqual(financePeriodLabels(dashboard.period_start, dashboard.period_end, dashboard.previous_period_start, dashboard.previous_period_end), {
    current: '01/09/2026 → trước 12:30 07/09/2026',
    previous: '01/08/2026 → trước 00:00 01/09/2026',
  })
  assert.deepEqual(financePeriodLabels('2026-01-01T00:00:00+07:00', '2026-02-01T00:00:00+07:00', '2025-12-01T00:00:00+07:00', '2026-01-01T00:00:00+07:00'), {
    current: '01/01/2026 → trước 00:00 01/02/2026',
    previous: '01/12/2025 → trước 00:00 01/01/2026',
  })
  assert.equal(financePeriodLabels('2026-10-01T00:00:00+07:00', '2026-10-01T00:00:00+07:00', null, null).current, 'Kỳ chưa bắt đầu')
})

test('rhythm helpers retain sparse-positive activity without inventing missed reminders', () => {
  expect(daysInReportMonth('2026-02')).toHaveLength(28)
  expect(reportMonthOffset('2026-09')).toBe(1)
  const counts = activityCountByTrackerDay([{ tracker_id: 'food', day: '2026-09-02', count: 2 }, { tracker_id: 'food', day: '2026-09-03', count: 0 }])
  expect(counts.get('food:2026-09-02')).toBe(2)
  expect(counts.has('food:2026-09-03')).toBe(false)
})

test('finance dashboard exposes exact amounts and resolves empty group tracker names', () => {
  const html = render()
  assert.match(html, /Đã chi trong kỳ/)
  assert.match(html, /300\.000/)
  assert.match(html, /400\.000/)
  assert.match(html, /Ít hơn 100\.000/)
  assert.match(html, /Ăn uống/)
  assert.match(html, /Nhịp ghi hiện tại/)
  assert.match(html, /Khoản cố định hiện tại/)
  assert.doesNotMatch(html, /dashboard-refreshing|live and fresh/)
})

test('a historical month ending at the next calendar boundary is not called partial', () => {
  const html = render({ ...dashboard,
    period_start: '2026-08-01T00:00:00+07:00',
    period_end: '2026-09-01T00:00:00+07:00',
    finance_months: [{ month: '2026-08', period_start: '2026-08-01T00:00:00+07:00', period_end: '2026-09-01T00:00:00+07:00', total: 300_000 }],
    activity_month: '2026-08',
  })
  assert.doesNotMatch(html, /Kỳ đang xem chưa trọn tháng/)
})

test('insufficient rhythm trackers stay reachable in one closed disclosure', () => {
  const html = render()
  assert.match(html, /2 tracker chưa đủ dữ liệu để tính nhịp/)
  assert.match(html, /Đi bộ/)
  assert.match(html, /Đọc sách/)
  assert.match(html, /2 ngày · TB 3 ngày/)
  assert.doesNotMatch(html, /<details[^>]*open=/)
})

test('signed composition has a visible zero explanation and no false percentage', () => {
  const html = render({ ...dashboard, f3_groups: [
    { name: 'Chi', total: 300, trackers: [] },
    { name: 'Điều chỉnh', total: -100, trackers: [] },
  ] })
  assert.match(html, /Có số âm: vạch đứng là 0/)
  assert.doesNotMatch(html, />\d+%<\/span>/)
  assert.match(html, /-100/)
})

test('errors hide cached financial content and zero scheduled amounts are not missing subscriptions', () => {
  const failed = render(dashboard, new Error('offline'))
  assert.match(failed, /role="alert"/)
  assert.match(failed, /Thử lại/)
  assert.doesNotMatch(failed, /300\.000|Ăn uống/)
  const zero = render({ ...dashboard, f6: { ...dashboard.f6, subscription_count: 1 } })
  assert.match(zero, /0.*\/ tháng/)
  assert.doesNotMatch(zero, /Chưa có khoản cố định nào/)
})

test('corruption warnings remain visible and a missing preceding full window is not a misleading delta', () => {
  const html = render({ ...dashboard, prev_period_days: 0, previous_period_start: null, previous_period_end: null, corrupted_entry_count: 2,
    f6: { ...dashboard.f6, corrupted_subscription_count: 1 } })
  assert.match(html, /2 bản ghi không đọc được/)
  assert.match(html, /1 bản ghi không đọc được/)
  assert.match(html, /Chưa tính được tổng/)
  assert.doesNotMatch(html, /Chưa có khoản cố định nào/)
  assert.match(html, /Chưa có kỳ trước để so sánh/)
  assert.doesNotMatch(html, /Ít hơn 100\.000/)
})
