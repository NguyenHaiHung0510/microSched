import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { formatVnd, type DashboardResponse, type Tracker } from '@/tracker-ui'

function moneyClass(value: number): string {
  return value < 0 ? 'text-bad' : 'text-ok'
}

export function DashboardPanel({
  dashboard,
  monthLabel,
  trackers,
  loading,
  error,
  refetching,
  onRetry,
}: {
  dashboard: DashboardResponse | null
  monthLabel: string
  trackers: Tracker[]
  loading: boolean
  error: unknown
  refetching: boolean
  onRetry: () => void
}) {
  const trackerName = (id: string): string =>
    trackers.find((tracker) => tracker.id === id)?.name ?? 'Đã archive'

  if (error) {
    return (
      <Card
        data-testid="dashboard-error"
        className="gap-3 p-4 shadow-1 ring-0"
        role="alert"
      >
        <p className="text-sm text-bad">Không tải được dữ liệu tài chính.</p>
        <Button variant="outline" size="lg" className="min-h-11" onClick={onRetry}>
          Thử lại
        </Button>
      </Card>
    )
  }

  if (loading || !dashboard) {
    return (
      <Card data-testid="dashboard-panel" className="gap-3 p-4 shadow-1 ring-0">
        <h2 className="text-base font-bold">Tài chính {monthLabel}</h2>
        <p data-testid="dashboard-loading" className="text-sm text-muted-foreground">
          Đang tải…
        </p>
      </Card>
    )
  }

  const f2Delta = dashboard.f2_current - dashboard.f2_previous
  const f2Direction = f2Delta > 0 ? 'nhiều hơn' : f2Delta < 0 ? 'ít hơn' : 'bằng'
  const a4Label =
    dashboard.a4_trend.trend === 'up'
      ? 'Đang tăng'
      : dashboard.a4_trend.trend === 'down'
        ? 'Đang giảm'
        : 'Ổn định'

  return (
    <div data-testid="dashboard-panel" className="space-y-4">
      {refetching ? (
        <p data-testid="dashboard-refreshing" className="text-xs text-muted-foreground">
          Đang cập nhật…
        </p>
      ) : null}
      {dashboard.corrupted_entry_count > 0 ? (
        <div className="space-y-1 rounded-lg bg-warn-bg p-4" role="alert">
          <p className="text-sm font-bold text-warn">
            {dashboard.corrupted_entry_count} bản ghi không đọc được
          </p>
          <p className="text-sm text-warn">
            Số liệu có thể thiếu — kiểm tra khoá mã hoá hoặc dữ liệu gốc.
          </p>
        </div>
      ) : null}

      <Card className="gap-3 p-4 shadow-1 ring-0">
        <h2 className="text-base font-bold">Tài chính {monthLabel}</h2>
        <div className="space-y-3">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-sm font-semibold">Đã chi tháng này</span>
            <span
              data-testid="dashboard-f1-total"
              className="text-xl font-extrabold tabular-nums"
            >
              {formatVnd(dashboard.f1_total)}
            </span>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-sm font-semibold">So cùng kỳ tháng trước</span>
            <div className="text-right">
              <p
                data-testid="dashboard-f2-compare"
                className={`text-lg font-bold tabular-nums ${moneyClass(f2Delta)}`}
              >
                {f2Direction} {formatVnd(Math.abs(f2Delta))}
              </p>
              <p className="text-xs text-muted-foreground">
                {formatVnd(dashboard.f2_current)} · kỳ trước {formatVnd(dashboard.f2_previous)}
              </p>
            </div>
          </div>
          {dashboard.prev_period_truncated ? (
            <p className="text-xs text-warn">
              Kỳ trước chỉ có {dashboard.prev_period_days} ngày (tháng ngắn hơn).
            </p>
          ) : null}
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-sm font-semibold">Chênh lệch thu – chi</span>
            <span
              data-testid="dashboard-f5-net"
              className={`text-lg font-extrabold tabular-nums ${moneyClass(dashboard.f5_net)}`}
            >
              {formatVnd(dashboard.f5_net)}
            </span>
          </div>
        </div>
      </Card>

      {dashboard.f3_groups.length > 0 ? (
        <Card className="gap-3 p-4 shadow-1 ring-0">
          <h3 className="text-base font-bold">Theo nhóm</h3>
          <div className="space-y-2">
            {dashboard.f3_groups.map((group) => (
              <div
                key={group.name}
                data-testid="dashboard-f3-group"
                className="rounded-lg bg-muted/50 p-3"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-sm font-bold">{group.name}</span>
                  <span className="text-sm font-bold tabular-nums">
                    {formatVnd(group.total)}
                  </span>
                </div>
                {group.trackers.map((line) => (
                  <div
                    key={line.tracker_id}
                    className="mt-1 flex items-baseline justify-between gap-3"
                  >
                    <span className="text-sm text-muted-foreground">{line.name}</span>
                    <span className="text-sm tabular-nums">{formatVnd(line.total)}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      {dashboard.f4_top.length > 0 ? (
        <Card className="gap-3 p-4 shadow-1 ring-0">
          <h3 className="text-base font-bold">Khoản chi lớn nhất</h3>
          <div className="space-y-2">
            {dashboard.f4_top.map((line) => (
              <div
                key={line.entry_id}
                data-testid="dashboard-f4-top"
                className="flex items-baseline justify-between gap-3"
              >
                <span className="min-w-0 break-words text-sm">{line.tracker_name}</span>
                <span className="text-sm font-bold tabular-nums">{formatVnd(line.amount)}</span>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      <Card className="gap-3 p-4 shadow-1 ring-0">
        <h3 className="text-base font-bold">Hành vi</h3>
        <div data-testid="dashboard-a3-counts" className="flex flex-wrap gap-2">
          <span className="rounded-lg bg-muted/50 px-3 py-1.5 text-sm">
            Tuần này: <b className="tabular-nums">{dashboard.a3_counts.week}</b>
          </span>
          <span className="rounded-lg bg-muted/50 px-3 py-1.5 text-sm">
            Tháng này: <b className="tabular-nums">{dashboard.a3_counts.month}</b>
          </span>
          <span className="rounded-lg bg-muted/50 px-3 py-1.5 text-sm">
            Năm nay: <b className="tabular-nums">{dashboard.a3_counts.year}</b>
          </span>
        </div>
        <p data-testid="dashboard-a4-trend" className="text-sm">
          Tháng này{' '}
          <b className="tabular-nums">{dashboard.a4_trend.current_month}</b> lần ghi, trung bình
          3 tháng trước <b className="tabular-nums">{dashboard.a4_trend.prev_avg}</b> —{' '}
          <span className="font-bold">{a4Label}</span>
        </p>
      </Card>

      {dashboard.a2_gap.length > 0 ? (
        <Card className="gap-3 p-4 shadow-1 ring-0">
          <h3 className="text-base font-bold">Nhịp ghi gần đây</h3>
          <div data-testid="dashboard-a2-gap" className="space-y-2">
            {dashboard.a2_gap.map((line) => (
              <div key={line.tracker_id} className="flex items-baseline justify-between gap-3">
                <span className="min-w-0 break-words text-sm text-muted-foreground">
                  {trackerName(line.tracker_id)}
                </span>
                <span className="text-sm tabular-nums">
                  {line.enough
                    ? `${line.current_days} ngày · TB ${line.avg_days} ngày`
                    : 'chưa đủ dữ liệu'}
                </span>
              </div>
            ))}
          </div>
        </Card>
      ) : null}
    </div>
  )
}
