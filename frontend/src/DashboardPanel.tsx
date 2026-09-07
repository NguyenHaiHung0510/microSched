import type { ReactNode } from 'react'

import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { FinanceComparison, FinanceComposition } from '@/FinanceChart'
import { daysLeftLabel, formatShortDate } from '@/subscription-ui'
import { formatVnd, type DashboardResponse, type Tracker } from '@/tracker-ui'

export function DashboardPanel({
  dashboard,
  monthLabel,
  financeExtra,
  trackers,
  loading,
  error,
  onRetry,
}: {
  dashboard: DashboardResponse | null
  monthLabel: string
  financeExtra?: ReactNode
  trackers: Tracker[]
  loading: boolean
  error: unknown
  // Kept optional for existing callers while freshness moves to the app header.
  lastSuccessAt?: number | null
  queryStatus?: 'success' | 'error' | 'pending'
  onRetry: () => void
}) {
  const trackerName = (id: string): string =>
    trackers.find((tracker) => tracker.id === id)?.name ?? 'Đã lưu trữ'

  if (error) {
    return (
      <Card data-testid="dashboard-error" className="gap-3 p-4 shadow-1 ring-0" role="alert">
        {financeExtra}
        <p className="text-sm text-bad">Không tải được dữ liệu tài chính.</p>
        <Button variant="outline" size="lg" className="min-h-11" onClick={onRetry}>Thử lại</Button>
      </Card>
    )
  }

  if (loading || !dashboard) {
    return (
      <Card data-testid="dashboard-panel" className="gap-3 p-4 shadow-1 ring-0">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-bold">Tài chính {monthLabel}</h2>
          {financeExtra}
        </div>
        <p data-testid="dashboard-loading" className="text-sm text-muted-foreground" role="status">Đang tải…</p>
      </Card>
    )
  }

  const a4Label = dashboard.a4_trend.trend === 'up'
    ? 'Đang tăng'
    : dashboard.a4_trend.trend === 'down' ? 'Đang giảm' : 'Ổn định'
  const enoughGaps = dashboard.a2_gap.filter((line) => line.enough)
  const insufficientGaps = dashboard.a2_gap.filter((line) => !line.enough)

  return (
    <div data-testid="dashboard-panel" className="space-y-3">
      {dashboard.corrupted_entry_count > 0 ? (
        <div className="space-y-1 rounded-lg bg-warn-bg p-4" role="alert">
          <p className="text-sm font-bold text-foreground">{dashboard.corrupted_entry_count} bản ghi không đọc được</p>
          <p className="text-sm text-foreground">Số liệu có thể thiếu — kiểm tra khoá mã hoá hoặc dữ liệu gốc.</p>
        </div>
      ) : null}

      <Card className="gap-4 p-4 shadow-1 ring-0">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-bold">Tài chính {monthLabel}</h2>
          {financeExtra}
        </div>
        <dl className="grid grid-cols-1 gap-3 rounded-lg bg-muted/50 p-3 sm:grid-cols-2">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 sm:block">
            <dt className="text-sm text-muted-foreground">Đã chi trong kỳ</dt>
            <dd data-testid="dashboard-f1-total" className="break-words text-xl font-extrabold tabular-nums sm:text-2xl">{formatVnd(dashboard.f1_total)}</dd>
          </div>
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 sm:block">
            <dt className="text-sm text-muted-foreground">Thu − chi</dt>
            <dd data-testid="dashboard-f5-net" className={`break-words text-xl font-bold tabular-nums ${dashboard.f5_net < 0 ? 'text-bad' : 'text-foreground'}`}>
              {formatVnd(dashboard.f5_net)}
            </dd>
          </div>
        </dl>
        <FinanceComparison dashboard={dashboard} />
        <div className="border-t border-muted pt-3"><FinanceComposition groups={dashboard.f3_groups} trackerName={trackerName} /></div>

        {dashboard.f4_top.length > 0 ? (
          <details className="border-t border-muted pt-1">
            <summary className="min-h-11 cursor-pointer content-center rounded-md text-sm font-bold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
              Khoản chi lớn nhất <span className="font-normal text-muted-foreground">· {dashboard.f4_top.length} bản ghi</span>
            </summary>
            <ol className="divide-y divide-muted">
              {dashboard.f4_top.map((line) => (
                <li key={line.entry_id} data-testid="dashboard-f4-top" className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2 text-sm">
                  <span className="min-w-0 break-words">{line.tracker_name}</span>
                  <span className="font-semibold tabular-nums">{formatVnd(line.amount)}</span>
                </li>
              ))}
            </ol>
          </details>
        ) : null}
      </Card>

      <Card className="gap-3 p-4 shadow-1 ring-0">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <h3 className="text-sm font-bold">Khoản cố định hiện tại</h3>
          <span data-testid="dashboard-f6-burn" className="text-sm font-semibold tabular-nums">
            {dashboard.f6.subscription_count > 0
              ? `${dashboard.f6.monthly_burn > 0 ? '≈ ' : ''}${formatVnd(dashboard.f6.monthly_burn)} / tháng`
              : dashboard.f6.corrupted_subscription_count > 0 ? 'Chưa tính được tổng' : 'Chưa có khoản cố định nào'}
          </span>
        </div>
        {dashboard.f6.corrupted_subscription_count > 0 ? (
          <p className="rounded-md bg-warn-bg p-2 text-sm text-foreground" role="alert">
            {dashboard.f6.corrupted_subscription_count} bản ghi không đọc được — số liệu có thể thiếu
          </p>
        ) : null}
        {dashboard.f6.subscription_count > 0 ? <p className="text-xs text-muted-foreground">{dashboard.f6.subscription_count} khoản tự gia hạn</p> : null}
        {dashboard.f6.upcoming.length > 0 ? (
          <div data-testid="dashboard-f6-upcoming" className="divide-y divide-muted">
            {dashboard.f6.upcoming.map((item) => (
              <div key={item.subscription_id} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2">
                <div className="min-w-0">
                  <p className="break-words text-sm font-semibold">{item.name}</p>
                  <p className="text-xs text-muted-foreground tabular-nums">{formatShortDate(item.expires_on)} · {daysLeftLabel(item.days_left)}</p>
                </div>
                <span className="text-sm font-semibold tabular-nums">
                  {item.corrupted ? 'không đọc được' : item.amount != null ? formatVnd(item.amount) : 'Chưa có số tiền'}
                </span>
              </div>
            ))}
          </div>
        ) : null}
      </Card>

      <Card className="gap-3 p-4 shadow-1 ring-0">
        <h3 className="text-sm font-bold">Nhịp ghi hiện tại</h3>
        <dl data-testid="dashboard-a3-counts" className="grid grid-cols-3 gap-3">
          {[
            ['Tuần này', dashboard.a3_counts.week],
            ['Tháng này', dashboard.a3_counts.month],
            ['Năm nay', dashboard.a3_counts.year],
          ].map(([label, count]) => (
            <div key={label}>
              <dt className="text-xs text-muted-foreground">{label}</dt>
              <dd className="text-lg font-bold tabular-nums">{count}</dd>
            </div>
          ))}
        </dl>
        <p data-testid="dashboard-a4-trend" className="text-xs text-muted-foreground">
          Tháng này <b className="tabular-nums">{dashboard.a4_trend.current_month}</b> lần ghi · TB 3 tháng trước <b className="tabular-nums">{dashboard.a4_trend.prev_avg}</b> · {a4Label}
        </p>
        {dashboard.a2_gap.length > 0 ? (
          <div data-testid="dashboard-a2-gap" className="space-y-2 border-t border-muted pt-3">
            {enoughGaps.map((line) => (
              <div key={line.tracker_id} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm">
                <span className="min-w-0 break-words">{trackerName(line.tracker_id)}</span>
                <span className="text-muted-foreground tabular-nums">{line.current_days ?? '—'} ngày · TB {line.avg_days ?? '—'} ngày</span>
              </div>
            ))}
            {insufficientGaps.length > 0 ? (
              <details data-testid="dashboard-insufficient-rhythm">
                <summary className="min-h-11 cursor-pointer content-center rounded-md text-sm text-muted-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
                  {insufficientGaps.length} tracker chưa đủ dữ liệu để tính nhịp
                </summary>
                <ul className="space-y-1 pb-1 pl-4 text-sm text-muted-foreground">
                  {insufficientGaps.map((line) => <li key={line.tracker_id} className="break-words">{trackerName(line.tracker_id)}</li>)}
                </ul>
              </details>
            ) : null}
          </div>
        ) : null}
      </Card>
    </div>
  )
}
