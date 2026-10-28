import { expect, test } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MimiResponseTiming } from './MimiResponseTiming'
import { MimiMetricsTable } from './MimiConversationMetrics'
import type { MimiConversation, MimiResponseTimings } from './mimi-api'

const timings: MimiResponseTimings = {
  version: 1, scope: 'all_retained_response_segments', provenance: 'client_observed',
  min_ms: 2000, avg_ms: 5000, max_ms: 8000, observed: 2, eligible: 3, missing: 1,
  pending: 1, failed: 1, cancelled: 1, unknown: 1,
  responses: [{ run_id: 'r', target_id: 'm', phase: 'confirmation', source_id: 'preview',
    response_kind: 'receipt', outcome: 'succeeded', parent_run_id: null, elapsed_ms: 2000,
    observation: 'visible_paint', provenance: 'client_observed' }],
}
const conversation = { response_timings: timings, metrics: { responses: [{ run_id: 'r', usd: { known: '0.03', complete: true } }] } } as unknown as MimiConversation

test('answer shows exact phase timing beside same-run cost, with no second charge', () => {
  const html = renderToStaticMarkup(<MimiResponseTiming conversation={conversation} targetId="m" />)
  expect(html).toContain('2 giây')
  expect(html).toContain('sau xác nhận')
  expect(html).toContain('$0.03')
  expect(html).toContain('phí cùng run, không cộng lại')
})

test('conversation summary shows arithmetic metrics with response denominator and exclusions', () => {
  const html = renderToStaticMarkup(<MimiMetricsTable conversation={{ response_timings: timings } as MimiConversation} />)
  expect(html).toContain('2 giây / 5 giây / 8 giây')
  expect(html).toContain('2/3 phản hồi thành công có đo')
  expect(html).toContain('1 thiếu')
  expect(html).toContain('không phải provider latency')
  expect(html).toContain('không vào min/TB/max thành công')
})

test('hidden and legacy stay missing without substituting server elapsed or zero', () => {
  const hidden = { ...conversation, response_timings: { ...timings, responses: [{ ...timings.responses[0], elapsed_ms: null, observation: 'hidden' }] } }
  const html = renderToStaticMarkup(<MimiResponseTiming conversation={hidden} targetId="m" />)
  expect(html).toContain('E2E —')
  expect(html).toContain('ẩn trong lúc đo')
  expect(html).not.toContain('0 giây')
})
