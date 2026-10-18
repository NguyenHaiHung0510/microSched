import type { MimiAccountingSummary, MimiConversation } from '@/mimi-api'
import { lastMeasuredInput, formatMetric } from '@/mimi-context-metrics'
import { mimiRunLabel } from '@/mimi-presentation'

const money = (value: string | null) => value == null ? '—' : `$${value}`
const coverage = (observed: number, missing: number) => `${observed}/${observed + missing} call${missing ? ` · ${missing} chưa có số liệu` : ''}`

export function MimiMetricsTable({ conversation }: { conversation: MimiConversation }) {
  const metrics = conversation.metrics
  const context = lastMeasuredInput(conversation)
  const rows = [
    ['Context đã đo', `${formatMetric(context)} / 400k`, `Lần đo gần nhất · context hiện tại chưa đo lại${metrics?.last_measured_input ? ` · ${new Date(metrics.last_measured_input.as_of).toLocaleString('vi-VN')}` : ''}`],
    ['Ngưỡng compact mềm', metrics?.context_policy ? formatMetric(metrics.context_policy.compaction_trigger_tokens) : '—', 'Tách biệt mốc vận hành 400k · dùng input native đủ điều kiện'],
    ['USD đã ghi nhận', metrics ? money(metrics.usd.known) : '—', metrics ? coverage(metrics.usd.observed, metrics.usd.missing) : 'Chưa có tổng hợp từ server'],
    ['Input tích lũy', formatMetric(metrics?.input.known), metrics ? coverage(metrics.input.observed, metrics.input.missing) : ''],
    ['Output tổng (gồm reasoning)', formatMetric(metrics?.output.known), metrics ? coverage(metrics.output.observed, metrics.output.missing) : ''],
    ['Reasoning (nằm trong output)', formatMetric(metrics?.reasoning.known), metrics ? coverage(metrics.reasoning.observed, metrics.reasoning.missing) : ''],
    ['Cache hit theo token input', metrics?.cache.ratio == null ? '—' : `${(100 * metrics.cache.ratio).toLocaleString('vi-VN', { maximumFractionDigits: 1 })}%`, metrics ? `${formatMetric(metrics.cache.cached)} / ${formatMetric(metrics.cache.sample_input)} input cùng mẫu · ${coverage(metrics.cache.observed, metrics.cache.missing)}` : ''],
    ['Output / thời gian call', '—', 'Chưa có tử số và khoảng đo tương ứng được công bố'],
  ]
  return <div data-testid="mimi-metrics-summary"><div className="overflow-hidden rounded-xl border"><table className="w-full table-fixed text-left text-sm"><caption className="sr-only">Thống kê hội thoại</caption><tbody>{rows.map(([label, value, note]) => <tr key={label} className="border-b last:border-0"><th scope="row" className="w-1/2 p-3 font-medium">{label}</th><td className="min-w-0 break-words p-3 tabular-nums [overflow-wrap:anywhere]">{value}{note ? <p className="mt-1 text-xs text-muted-foreground">{note}</p> : null}</td></tr>)}</tbody></table></div>{metrics ? <div className="mt-3 space-y-1 text-xs text-muted-foreground"><p>{metrics.eligible_dispatches} dispatch · main {metrics.purpose_counts.main} · helper {metrics.purpose_counts.helper}{metrics.purpose_counts.unclassified ? ` · chưa phân loại ${metrics.purpose_counts.unclassified}` : ''} · {metrics.reused_calls} lượt dùng lại, không cộng phí</p><p>Phạm vi: receipts còn lưu của hội thoại{metrics.scope_complete ? '' : ' · chưa đầy đủ'}. Native token traffic khác với context đang giữ.</p><p>Cập nhật {new Date(metrics.as_of).toLocaleString('vi-VN')}{metrics.anomaly_dispatches ? ` · ${metrics.anomaly_dispatches} dispatch có số liệu mâu thuẫn` : ''}</p></div> : null}</div>
}

function ResponseValues({ row }: { row: MimiAccountingSummary }) {
  return <><td className="p-2 tabular-nums">{money(row.usd.known)}<p className="text-xs text-muted-foreground">{coverage(row.usd.observed, row.usd.missing)}</p></td><td className="p-2 tabular-nums">{formatMetric(row.output.known)}<p className="text-xs text-muted-foreground">{coverage(row.output.observed, row.output.missing)}</p></td><td className="p-2">—</td></>
}

export function MimiConversationMetrics({ conversation }: { conversation: MimiConversation }) {
  const rows = conversation.metrics?.responses ?? []
  return <div className="space-y-4"><MimiMetricsTable conversation={conversation} /><details className="rounded-xl border" data-testid="mimi-metrics-responses"><summary className="cursor-pointer p-3 text-sm font-semibold">Theo phản hồi ({rows.length})</summary><div className="max-h-80 overflow-auto"><table className="w-full text-left text-xs"><thead className="sticky top-0 bg-card"><tr><th className="p-2">Phản hồi / lượt</th><th className="p-2">USD</th><th className="p-2">Output</th><th className="p-2">token/s</th></tr></thead><tbody>{rows.map((row, i) => <tr key={row.run_id ?? 'unassigned'} className="border-t"><th scope="row" className="p-2 font-medium">{row.run_id == null ? 'Chưa gắn lượt' : row.assistant_message_id ? `Phản hồi ${i + 1}` : `Lượt ${i + 1} · chưa có câu trả lời`}<p className="text-xs font-normal text-muted-foreground">{mimiRunLabel(row.state)}</p></th><ResponseValues row={row} /></tr>)}</tbody></table></div></details></div>
}
