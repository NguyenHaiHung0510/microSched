import type { MimiAccountingSummary, MimiConversation } from '@/mimi-api'
import { lastMeasuredInput, formatMetric } from '@/mimi-context-metrics'
import { mimiRunLabel } from '@/mimi-presentation'

const money = (value: string | null) => value == null ? '—' : `$${value}`
const coverage = (observed: number, missing: number) => `${observed}/${observed + missing} call${missing ? ` · ${missing} chưa có số liệu` : ''}`

export function MimiMetricsTable({ conversation }: { conversation: MimiConversation }) {
  const metrics = conversation.metrics
  const rows = [
    ['Context đã đo', `${formatMetric(lastMeasuredInput(conversation))} / 400k`, metrics?.last_measured_input ? new Date(metrics.last_measured_input.as_of).toLocaleString('vi-VN') : ''],
    ['Ngưỡng compact mềm', formatMetric(metrics?.context_policy?.compaction_trigger_tokens), ''],
    ['USD đã ghi nhận', metrics ? money(metrics.usd.known) : '—', ''],
    ['Input tích lũy', formatMetric(metrics?.input.known), ''],
    ['Output (gồm reasoning)', formatMetric(metrics?.output.known), ''],
    ['Reasoning (trong output)', formatMetric(metrics?.reasoning.known), ''],
    ['Cache hit', metrics?.cache.ratio == null ? '—' : `${(100 * metrics.cache.ratio).toLocaleString('vi-VN', { maximumFractionDigits: 1 })}%`, ''],
  ]
  const incomplete = !metrics || !metrics.scope_complete || metrics.anomaly_dispatches > 0
    || [metrics.input, metrics.output, metrics.reasoning, metrics.usd, metrics.cache].some((value) => !value.complete)
  return <div data-testid="mimi-metrics-summary">
    <div className="overflow-hidden rounded-xl border"><table className="w-full table-fixed text-left text-sm"><caption className="sr-only">Thống kê hội thoại</caption><tbody>{rows.map(([label, value, note]) => <tr key={label} className="border-b last:border-0"><th scope="row" className="w-1/2 px-3 py-2 font-medium">{label}</th><td className="min-w-0 break-words px-3 py-2 tabular-nums [overflow-wrap:anywhere]">{value}{note ? <p className="mt-1 text-xs text-muted-foreground">{note}</p> : null}</td></tr>)}</tbody></table></div>
    <details className="mt-2 text-xs text-muted-foreground" data-testid="mimi-metrics-coverage"><summary className="cursor-pointer py-1">{incomplete ? 'Số liệu chưa đầy đủ · chi tiết' : 'Nguồn và phạm vi'}</summary>
      <p className="mt-1">Context là lần đo gần nhất; context hiện tại chưa đo lại. Native input gồm cache; reasoning nằm trong output.</p>
      {metrics ? <><dl className="mt-1 space-y-1">{(['input', 'output', 'reasoning', 'usd'] as const).map((key) => <div key={key}><dt className="inline font-semibold">{key}: </dt><dd className="inline">{coverage(metrics[key].observed, metrics[key].missing)}</dd></div>)}<div><dt className="inline font-semibold">Cache: </dt><dd className="inline">{formatMetric(metrics.cache.cached)} / {formatMetric(metrics.cache.sample_input)} input cùng mẫu · {coverage(metrics.cache.observed, metrics.cache.missing)}</dd></div></dl><p className="mt-1">{metrics.eligible_dispatches} dispatch · main {metrics.purpose_counts.main} · helper {metrics.purpose_counts.helper} · chưa phân loại {metrics.purpose_counts.unclassified} · {metrics.reused_calls} lượt dùng lại, không cộng phí.</p><p>Receipts còn lưu{metrics.scope_complete ? '' : ' · phạm vi chưa đầy đủ'} · cập nhật {new Date(metrics.as_of).toLocaleString('vi-VN')}{metrics.anomaly_dispatches ? ` · ${metrics.anomaly_dispatches} dispatch mâu thuẫn` : ''}.</p></> : <p>Chưa có tổng hợp từ server.</p>}
      <p>Output / thời gian call: — (chưa có khoảng đo tương ứng).</p>
    </details>
  </div>
}

export function MimiTokenPrices({ conversation }: { conversation: MimiConversation }) {
  const prices = conversation.metrics?.token_prices
  const rows = [['input_uncached', 'Input không cache'], ['cache_read', 'Cache read'], ['output', 'Output']] as const
  return <details className="rounded-xl border" data-testid="mimi-token-prices"><summary className="cursor-pointer p-3 text-sm font-semibold">Giá token · USD / 1M{!prices || prices.unknown_dispatches || prices.partial_dispatches ? ' · chưa đầy đủ' : ''}</summary>
    <div className="overflow-x-auto"><table className="w-full min-w-72 text-right text-xs tabular-nums"><caption className="sr-only">Đơn giá thực tế từ billing đã đối soát</caption><thead><tr className="border-t"><th className="p-2 text-left" scope="col">Token</th><th className="p-2" scope="col">Min</th><th className="p-2" scope="col"><abbr title="Trung bình theo số token của từng nhóm">TB</abbr></th><th className="p-2" scope="col">Max</th></tr></thead><tbody>{rows.map(([key, label]) => <tr className="border-t" key={key}><th scope="row" className="p-2 text-left font-medium">{label}</th>{(['min', 'weighted_average', 'max'] as const).map((field) => <td className="whitespace-nowrap p-2" key={field}>{prices?.[key]?.[field] == null ? '—' : `$${Number(prices[key][field]).toLocaleString('vi-VN', { maximumSignificantDigits: 6 })}`}</td>)}</tr>)}</tbody></table></div>
    <div className="space-y-1 border-t p-3 text-xs text-muted-foreground"><p>TB theo token của từng nhóm. Input không cache dùng số token không cache; cache read chỉ lấy call có cache. Output gồm reasoning.</p><p>{prices ? `${prices.matched_dispatches} call có giá${prices.partial_dispatches ? ` (${prices.partial_dispatches} chỉ một phần)` : ''} · ${prices.unknown_dispatches} chưa xác định` : 'Chưa có billing đủ điều kiện.'}</p>{prices ? <p>{rows.map(([key, label]) => `${label}: ${prices[key].samples} mẫu / ${formatMetric(prices[key].tokens)} token${prices[key].unknown ? ` / ${prices[key].unknown} chưa rõ` : ''}${prices[key].not_applicable ? ` / ${prices[key].not_applicable} không áp dụng` : ''}`).join(' · ')}</p> : null}<p>Chỉ text-only, non-BYOK, đối soát phí; nhóm input/cache cần proof cache write riêng. “—” là chưa xác định hoặc không có mẫu áp dụng, không lấy giá catalog để bù.</p></div>
  </details>
}

function ResponseValues({ row }: { row: MimiAccountingSummary }) {
  return <><td className="p-2 tabular-nums">{money(row.usd.known)}<p className="text-xs text-muted-foreground">{coverage(row.usd.observed, row.usd.missing)}</p></td><td className="p-2 tabular-nums">{formatMetric(row.output.known)}<p className="text-xs text-muted-foreground">{coverage(row.output.observed, row.output.missing)}</p></td><td className="p-2">—</td></>
}

export function MimiConversationMetrics({ conversation }: { conversation: MimiConversation }) {
  const rows = conversation.metrics?.responses ?? []
  return <div className="space-y-3"><MimiMetricsTable conversation={conversation} /><MimiTokenPrices conversation={conversation} /><details className="rounded-xl border" data-testid="mimi-metrics-responses"><summary className="cursor-pointer p-3 text-sm font-semibold">Theo phản hồi ({rows.length})</summary><div className="max-h-80 overflow-auto"><table className="w-full text-left text-xs"><thead className="sticky top-0 bg-card"><tr><th className="p-2">Phản hồi / lượt</th><th className="p-2">USD</th><th className="p-2">Output</th><th className="p-2">token/s</th></tr></thead><tbody>{rows.map((row, i) => <tr key={row.run_id ?? 'unassigned'} className="border-t"><th scope="row" className="p-2 font-medium">{row.run_id == null ? 'Chưa gắn lượt' : row.assistant_message_id ? `Phản hồi ${i + 1}` : `Lượt ${i + 1} · chưa có câu trả lời`}<p className="text-xs font-normal text-muted-foreground">{mimiRunLabel(row.state)}</p></th><ResponseValues row={row} /></tr>)}</tbody></table></div></details></div>
}
