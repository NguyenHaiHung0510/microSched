import { financeBarScale, financePeriodLabels, financeShares } from '@/finance-chart'
import { formatVnd, type DashboardResponse } from '@/tracker-ui'

function ValueBar({
  value,
  scale,
  previous = false,
}: {
  value: number
  scale: ReturnType<typeof financeBarScale>
  previous?: boolean
}) {
  const bar = scale.bar(value)
  return (
    <div aria-hidden="true" className="relative h-2 rounded-full bg-muted">
      <span
        className={`absolute inset-y-0 rounded-full ${previous ? 'bg-muted-foreground' : 'bg-primary'}`}
        style={{ left: `${bar.left}%`, width: `${bar.width}%` }}
      />
      {scale.signed ? (
        <span className="absolute -inset-y-1 w-px bg-foreground" style={{ left: `${scale.zero}%` }} />
      ) : null}
    </div>
  )
}

export function FinanceComparison({ dashboard }: { dashboard: DashboardResponse }) {
  const scale = financeBarScale([dashboard.f2_previous, dashboard.f2_current])
  const delta = dashboard.f2_current - dashboard.f2_previous
  const direction = delta > 0 ? 'Nhiều hơn' : delta < 0 ? 'Ít hơn' : 'Bằng kỳ trước'
  const periods = financePeriodLabels(dashboard.period_start, dashboard.period_end, dashboard.prev_period_days)
  return (
    <figure data-testid="dashboard-finance-comparison" className="space-y-3">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="text-sm font-bold">So cùng kỳ tháng trước</span>
        <span data-testid="dashboard-f2-compare" className="text-sm font-semibold tabular-nums">
          {dashboard.prev_period_days === 0 ? 'Chưa đủ kỳ so sánh' : `${direction}${delta !== 0 ? ` ${formatVnd(Math.abs(delta))}` : ''}`}
        </span>
      </figcaption>
      <dl className="space-y-3">
        {[
          { label: 'Tháng trước · cùng kỳ', period: periods.previous, value: dashboard.f2_previous, previous: true },
          { label: 'Kỳ đang xem', period: periods.current, value: dashboard.f2_current, previous: false },
        ].map((row) => (
          <div key={row.label} className="space-y-1.5">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm">
              <dt className="text-muted-foreground">{row.label}</dt>
              <dd className="font-semibold tabular-nums">{formatVnd(row.value)}</dd>
            </div>
            <ValueBar value={row.value} scale={scale} previous={row.previous} />
            <p className="text-xs text-muted-foreground">{row.period}</p>
          </div>
        ))}
      </dl>
      {dashboard.prev_period_truncated ? (
        <p className="text-xs text-muted-foreground">
          Kỳ trước chỉ có {dashboard.prev_period_days} ngày (tháng ngắn hơn).
        </p>
      ) : null}
      {scale.signed ? <p className="text-xs text-muted-foreground">Vạch đứng là 0 ₫; số âm nằm bên trái.</p> : null}
    </figure>
  )
}

export function FinanceComposition({ groups, trackerName }: {
  groups: DashboardResponse['f3_groups']
  trackerName: (id: string) => string
}) {
  const scale = financeBarScale(groups.map((group) => group.total))
  const shares = financeShares(groups.map((group) => group.total))
  return (
    <section data-testid="dashboard-finance-composition" className="space-y-2">
      <h3 className="text-sm font-bold">Chi vào đâu</h3>
      {groups.length === 0 ? (
        <p className="text-sm text-muted-foreground">Chưa có khoản chi trong kỳ.</p>
      ) : (
        <div className="divide-y divide-muted">
          {groups.map((group, index) => (
            <details key={`${group.name}-${index}`} data-testid="dashboard-f3-group" className="group py-1">
              <summary className="min-h-11 cursor-pointer list-none space-y-2 rounded-md py-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
                <span className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm">
                  <span className="min-w-0 break-words font-semibold">
                    <span aria-hidden="true" className="mr-1 inline-block group-open:rotate-90">›</span>
                    {group.name}
                    {shares ? <span className="ml-2 text-xs font-normal text-muted-foreground">{Math.round(shares[index])}%</span> : null}
                  </span>
                  <span className="font-semibold tabular-nums">{formatVnd(group.total)}</span>
                </span>
                <ValueBar value={group.total} scale={scale} />
              </summary>
              <dl className="space-y-2 pb-2 pl-3 pt-1">
                {group.trackers.map((line) => (
                  <div key={line.tracker_id} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm">
                    <dt className="min-w-0 break-words text-muted-foreground">{line.name || trackerName(line.tracker_id)}</dt>
                    <dd className="tabular-nums">{formatVnd(line.total)}</dd>
                  </div>
                ))}
              </dl>
            </details>
          ))}
        </div>
      )}
      {scale.signed ? <p className="text-xs text-muted-foreground">Có số âm: vạch đứng là 0 ₫, không tính tỷ trọng.</p> : null}
    </section>
  )
}
