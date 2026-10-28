import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MimiConversationMetrics, MimiMetricsTable } from './MimiConversationMetrics'
import { MimiToolActivity } from './MimiToolActivity'
import type { MimiConversation, MimiConversationMetrics as Metrics, MimiEvent } from './mimi-api'

const value = (known: number | null) => ({ known, observed: known == null ? 0 : 1, missing: known == null ? 1 : 0, complete: known != null })
const metrics: Metrics = {
  version: 1, scope: 'all_retained_conversation_receipts', scope_complete: true,
  as_of: '2026-10-18T10:00:00Z', scope_start: '2026-10-18T09:00:00Z',
  provenance: 'server_receipts', retention: 'existing', reused_calls: 1,
  last_measured_input: { tokens: 64000, as_of: '2026-10-18T09:00:00Z', state: 'last_measured_current_projection_pending' },
  context_policy: { operating_input_tokens: 400000, compaction_trigger_tokens: 272000, current_projection_measurement: 'pending' },
  eligible_dispatches: 2, input: value(320000), output: value(48000), reasoning: value(36000),
  usd: { known: '0.042700001', observed: 1, missing: 1, complete: false },
  cache: { cached: 96000, sample_input: 320000, ratio: 0.3, observed: 1, missing: 1, complete: false },
  purpose_counts: { main: 1, helper: 1, unclassified: 0 }, anomaly_dispatches: 0,
  effective_completion_per_second: null, responses: [],
}

describe('P2 shared server snapshot', () => {
  it('renders exactly the same summary in pane and circle with explicit subsets, coverage and unknown speed', () => {
    const conversation = { metrics } as MimiConversation
    const table = renderToStaticMarkup(<MimiMetricsTable conversation={conversation} />)
    const pane = renderToStaticMarkup(<MimiConversationMetrics conversation={conversation} />)
    expect(pane).toContain(table)
    for (const expected of ['64.000 / 400k', '$0.042700001', '320.000', '48.000', '36.000', '30%', '96.000 / 320.000', '1 chưa có số liệu', 'nằm trong output', 'context hiện tại chưa đo lại', 'Ngưỡng compact mềm', '272.000']) expect(table).toContain(expected)
    expect(table).not.toContain('84.000')
    expect(table).not.toContain('Bytes')
    expect(pane).not.toContain('<details open')
  })
  it('price disclosure uses billing projection, token weighted average and honest absent cache samples', () => {
    const price = { min: '0.1', weighted_average: '0.19', max: '0.2', samples: 2, tokens: 1000 }
    const html = renderToStaticMarkup(<MimiConversationMetrics conversation={{ metrics: { ...metrics, token_prices: { unit: 'USD_per_1M_tokens', source: 'matched_native_billing', matched_dispatches: 2, unknown_dispatches: 1, input_uncached: price, output: { ...price, weighted_average: '0' }, cache_read: { min: null, weighted_average: null, max: null, samples: 0, tokens: 0 } } } } as MimiConversation} />)
    expect(html).toContain('Giá token · USD / 1M · chưa đầy đủ')
    expect(html).toContain('$0,19')
    expect(html).toContain('2 call có giá · 1 chưa xác định')
    expect(html).toContain('$0')
    expect(html).not.toContain('<details open')
    expect(renderToStaticMarkup(<MimiConversationMetrics conversation={{ metrics } as MimiConversation} />)).toContain('Chưa có billing đủ điều kiện')
  })
  it('labels output-only billing partial and distinguishes missing from not-applicable groups', () => {
    const unknown = { min: null, weighted_average: null, max: null, samples: 0, tokens: 0, unknown: 1, not_applicable: 0 }
    const output = { min: '0.5', weighted_average: '0.5', max: '0.5', samples: 1, tokens: 20, unknown: 0, not_applicable: 0 }
    const html = renderToStaticMarkup(<MimiConversationMetrics conversation={{ metrics: { ...metrics, token_prices: { unit: 'USD_per_1M_tokens', source: 'matched_native_billing', matched_dispatches: 1, partial_dispatches: 1, unknown_dispatches: 0, input_uncached: unknown, cache_read: { ...unknown, unknown: 0, not_applicable: 1 }, output } } } as MimiConversation} />)
    expect(html).toContain('Giá token · USD / 1M · chưa đầy đủ')
    expect(html).toContain('1 call có giá (1 chỉ một phần)')
    expect(html).toContain('1 chưa rõ')
    expect(html).toContain('1 không áp dụng')
    expect(html).toContain('$0,5')
    expect(html).not.toContain('$0<')
  })
  it('keeps failed and unassigned attempts, and missing USD distinct from a reported zero', () => {
    const row = { ...metrics, run_id: 'failed', assistant_message_id: null, state: 'halted', usd: { ...metrics.usd, known: null } }
    const html = renderToStaticMarkup(<MimiConversationMetrics conversation={{ metrics: { ...metrics, responses: [row, { ...row, run_id: null, state: 'unassigned', usd: { ...metrics.usd, known: '0' } }] } } as unknown as MimiConversation} />)
    expect(html).toContain('chưa có câu trả lời')
    expect(html).toContain('Chưa gắn lượt')
    expect(html).toContain('$0')
    expect(html).not.toContain('$null')
  })
  it('attaches collapsed query metadata once to the matching run and never makes an error zero matches', () => {
    const event = { run_id: 'run', sequence: 1, kind: 'tool.read_result', payload: { activity: {
      label: 'Đọc Task', state: 'error', query: { filter: { status: 'open', title_contains: 'mẫu' }, sort: 'updated_desc', limit: 20, projection: ['title'], cursor_present: true, has_next_page: false, count: null, coverage: 'unavailable', as_of: null, error: 'invalid_task_query_cursor', intrinsic_provenance: ['source_version', 'collection_version'] },
    } } } as unknown as MimiEvent
    const html = renderToStaticMarkup(<MimiToolActivity events={[event, event, { ...event, run_id: 'other' }]} runId="run" />)
    expect(html.match(/<details/g)).toHaveLength(1)
    expect(html).not.toContain('<details open')
    expect(html).toContain('chưa xác định số khớp')
    expect(html).toContain('Tiêu đề chứa: mẫu')
    expect(html).not.toContain('0 kết quả')
  })
})
