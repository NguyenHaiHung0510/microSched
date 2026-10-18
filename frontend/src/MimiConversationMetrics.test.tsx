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
    for (const expected of ['64.000 / 400k', '$0.042700001', '320.000', '48.000', '36.000', '30%', '96.000 / 320.000', '1 chưa có số liệu', 'nằm trong output', 'context hiện tại chưa đo lại']) expect(table).toContain(expected)
    expect(table).not.toContain('84.000')
    expect(table).not.toContain('Bytes')
    expect(pane).not.toContain('<details open')
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
