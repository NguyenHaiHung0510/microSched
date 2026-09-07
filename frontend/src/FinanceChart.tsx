import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { financeBarScale, financePeriodLabels, financeShares } from '@/finance-chart'
import { formatVnd, type DashboardResponse } from '@/tracker-ui'

type FinanceRow = { month: string; period_start: string; period_end: string; total: number }

function monthLabel(month: string): string {
  const [year, number] = month.split('-').map(Number)
  return new Intl.DateTimeFormat('vi-VN', { month: 'short', year: 'numeric' }).format(new Date(year, number - 1, 1))
}

function ValueBar({ value, scale, current = false }: { value: number; scale: ReturnType<typeof financeBarScale>; current?: boolean }) {
  const bar = scale.bar(value)
  return <div aria-hidden="true" className="relative h-3 rounded-full bg-muted">
    <span className={cn('absolute inset-y-0 rounded-full', current ? 'bg-ok' : 'bg-primary')} style={{ left: `${bar.left}%`, width: `${bar.width}%` }} />
    {scale.signed ? <span className="absolute -inset-y-1 w-px bg-foreground" style={{ left: `${scale.zero}%` }} /> : null}
  </div>
}

function chartRows(dashboard: DashboardResponse): FinanceRow[] {
  if (dashboard.report_months > 1) return dashboard.finance_months
  const selected = dashboard.finance_months[0]
  if (!selected || !dashboard.previous_period_start || !dashboard.previous_period_end) return dashboard.finance_months
  return [{ month: dashboard.previous_period_start.slice(0, 7), period_start: dashboard.previous_period_start, period_end: dashboard.previous_period_end, total: dashboard.f2_previous }, selected]
}

function nextMonthStart(month: string): string | null {
  const match = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(month)
  if (!match) return null
  const year = Number(match[1])
  const number = Number(match[2])
  return `${String(number === 12 ? year + 1 : year).padStart(4, '0')}-${String(number === 12 ? 1 : number + 1).padStart(2, '0')}-01`
}

function TrendLine({ rows }: { rows: FinanceRow[] }) {
  const values = rows.map((row) => row.total)
  const minimum = Math.min(0, ...values)
  const maximum = Math.max(0, ...values)
  const range = maximum - minimum || 1
  const x = (index: number) => rows.length === 1 ? 250 : 28 + (index * 464) / (rows.length - 1)
  const y = (value: number) => 142 - ((value - minimum) / range) * 110
  const path = rows.map((row, index) => `${index === 0 ? 'M' : 'L'} ${x(index)} ${y(row.total)}`).join(' ')
  return <div className="space-y-2" data-testid="finance-line-chart">
    <svg viewBox="0 0 520 154" className="w-full overflow-visible" role="img" aria-label="Xu hướng chi theo tháng; số tiền chính xác có trong bảng dữ liệu bên dưới">
      <line x1="28" x2="492" y1={y(0)} y2={y(0)} stroke="var(--border)" strokeDasharray="3 4" />
      <path d={path} fill="none" stroke="var(--primary)" strokeWidth="3" />
      {rows.map((row, index) => <circle key={row.month} cx={x(index)} cy={y(row.total)} r={index === rows.length - 1 ? 6 : 4} fill={index === rows.length - 1 ? 'var(--ok)' : 'var(--primary)'} />)}
    </svg>
    <div className="relative h-4 text-xs tabular-nums text-foreground" aria-hidden="true">
      {rows.map((row, index) => <span key={row.month} data-testid="finance-axis-label" className="absolute -translate-x-1/2" style={{ left: `${x(index) / 520 * 100}%` }}>{row.month.slice(5)}</span>)}
    </div>
    <p className="text-xs text-muted-foreground">Đường nét đứt là mốc 0 ₫; các tháng đi từ trái sang phải.</p>
  </div>
}

export function FinanceComparison({ dashboard }: { dashboard: DashboardResponse }) {
  const [chartKind, setChartKind] = useState<'bar' | 'line'>(dashboard.report_months >= 6 ? 'line' : 'bar')
  const rows = chartRows(dashboard)
  const scale = financeBarScale(rows.map((row) => row.total))
  const delta = dashboard.f2_current - dashboard.f2_previous
  const direction = delta > 0 ? 'Nhiều hơn' : delta < 0 ? 'Ít hơn' : 'Bằng kỳ trước'
  const periods = financePeriodLabels(dashboard.period_start, dashboard.period_end, dashboard.previous_period_start, dashboard.previous_period_end)
  const hasComparison = Boolean(dashboard.previous_period_start && dashboard.previous_period_end)
  const selectedMonth = dashboard.finance_months.at(-1)?.month
  const partial = selectedMonth ? dashboard.period_end.slice(0, 10) !== nextMonthStart(selectedMonth) : false

  return <figure data-testid="dashboard-finance-comparison" className="space-y-4 border-t border-muted pt-3">
    <figcaption className="space-y-2"><div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1"><span className="text-sm font-bold">So với kỳ trước trọn vẹn</span><span data-testid="dashboard-f2-compare" className="text-sm font-semibold tabular-nums">{hasComparison ? `${direction}${delta !== 0 ? ` ${formatVnd(Math.abs(delta))}` : ''}` : 'Chưa có kỳ trước để so sánh'}</span></div>{partial ? <p className="text-xs text-muted-foreground">{hasComparison ? 'Kỳ đang xem chưa trọn tháng; kỳ trước vẫn là một kỳ lịch đầy đủ.' : 'Kỳ đang xem chưa trọn tháng.'}</p> : null}</figcaption>
    <dl className="grid gap-3 rounded-lg bg-muted/50 p-3 sm:grid-cols-2"><div><dt className="text-sm text-muted-foreground">Kỳ trước trọn vẹn</dt><dd className="mt-1 font-semibold tabular-nums">{hasComparison ? formatVnd(dashboard.f2_previous) : '—'}</dd><p className="mt-1 text-xs text-muted-foreground">{periods.previous}</p></div><div><dt className="text-sm text-muted-foreground">Kỳ đang xem</dt><dd className="mt-1 font-semibold tabular-nums">{formatVnd(dashboard.f2_current)}</dd><p className="mt-1 text-xs text-muted-foreground">{periods.current}</p></div></dl>
    <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-bold">{dashboard.report_months === 1 ? 'Hai kỳ gần nhau' : 'Chi theo từng tháng'}</h3>{dashboard.report_months > 1 ? <div className="flex gap-1" role="group" aria-label="Kiểu biểu đồ tài chính"><Button size="lg" variant={chartKind === 'bar' ? 'selected' : 'ghost'} aria-pressed={chartKind === 'bar'} onClick={() => setChartKind('bar')}>Thanh</Button><Button size="lg" variant={chartKind === 'line' ? 'selected' : 'ghost'} aria-pressed={chartKind === 'line'} onClick={() => setChartKind('line')}>Đường</Button></div> : null}</div>
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="Chú giải biểu đồ"><span><span aria-hidden="true" className="mr-2 inline-block size-2.5 rounded-full bg-primary" />Lịch sử</span><span><span aria-hidden="true" className="mr-2 inline-block size-2.5 rounded-full bg-ok" />Tháng đang chọn</span></div>
    {chartKind === 'line' && rows.length > 1 ? <TrendLine rows={rows} /> : <dl className="space-y-4" data-testid="finance-bar-chart">{rows.map((row, index) => { const current = index === rows.length - 1; return <div key={row.month} className="space-y-1.5" data-testid="finance-month-bar"><div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm"><dt className="font-semibold">{monthLabel(row.month)}{current ? ' · đang chọn' : ''}</dt><dd className="font-semibold tabular-nums">{formatVnd(row.total)}</dd></div><ValueBar value={row.total} scale={scale} current={current} /></div> })}</dl>}
    {scale.signed ? <p className="text-xs text-muted-foreground">Có số âm: vạch đứng là 0 ₫; độ dài thanh biểu diễn giá trị có dấu.</p> : null}
    <details open={chartKind === 'line'} className="border-t border-muted pt-1"><summary className="min-h-11 cursor-pointer content-center rounded-md text-sm font-semibold focus-visible:outline-2 focus-visible:outline-ring">Số liệu theo tháng</summary><div className="overflow-x-auto"><table className="w-full min-w-64 text-left text-sm" data-testid="finance-month-table"><thead className="border-y border-muted text-xs text-muted-foreground"><tr><th scope="col" className="py-2 font-semibold">Tháng</th><th scope="col" className="py-2 text-right font-semibold">Đã chi</th></tr></thead><tbody>{rows.map((row, index) => <tr key={row.month} className="border-b border-muted/70"><th scope="row" className="py-2 font-medium">{monthLabel(row.month)}{index === rows.length - 1 ? ' · đang chọn' : ''}</th><td className="py-2 text-right font-semibold tabular-nums">{formatVnd(row.total)}</td></tr>)}</tbody></table></div></details>
  </figure>
}

export function FinanceComposition({ groups, trackerName }: { groups: DashboardResponse['f3_groups']; trackerName: (id: string) => string }) {
  const scale = financeBarScale(groups.map((group) => group.total))
  const shares = financeShares(groups.map((group) => group.total))
  return <section data-testid="dashboard-finance-composition" className="space-y-2"><h3 className="text-sm font-bold">Chi vào đâu <span className="font-normal text-muted-foreground">· kỳ đang xem</span></h3>{groups.length === 0 ? <p className="text-sm text-muted-foreground">Chưa có khoản chi trong kỳ đang xem.</p> : <div className="divide-y divide-muted">{groups.map((group, index) => <details key={`${group.name}-${index}`} data-testid="dashboard-f3-group" className="group py-1"><summary className="min-h-11 cursor-pointer list-none space-y-2 rounded-md py-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"><span className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm"><span className="min-w-0 break-words font-semibold"><span aria-hidden="true" className="mr-1 inline-block group-open:rotate-90">›</span>{group.name}{shares ? <span className="ml-2 text-xs font-normal text-muted-foreground">{Math.round(shares[index])}%</span> : null}</span><span className="font-semibold tabular-nums">{formatVnd(group.total)}</span></span><ValueBar value={group.total} scale={scale} /></summary><dl className="space-y-2 pb-2 pl-3 pt-1">{group.trackers.map((line) => <div key={line.tracker_id} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm"><dt className="min-w-0 break-words text-muted-foreground">{line.name || trackerName(line.tracker_id)}</dt><dd className="tabular-nums">{formatVnd(line.total)}</dd></div>)}</dl></details>)}</div>}{scale.signed ? <p className="text-xs text-muted-foreground">Có số âm: vạch đứng là 0 ₫, không tính tỷ trọng.</p> : null}</section>
}
