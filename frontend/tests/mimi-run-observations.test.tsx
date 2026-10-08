import { expect, test } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MimiRunObservations } from '../src/MimiRunObservations'
import type { MimiProviderCall, MimiRunObservation } from '../src/mimi-api'

const observation: MimiRunObservation = {
  known_cost_usd: 0.05, main_known_cost_usd: 0, helper_known_cost_usd: 0.05,
  unknown_cost_calls: 1, main_unknown_cost_calls: 1, helper_unknown_cost_calls: 0,
  cost_complete: false, main_calls: 1, helper_calls: 1, reused_calls: 1,
  elapsed_ms: 1000, context_observations: [], checkpoint_activations: 1,
  error_code: 'provider_refused',
}
const helper: MimiProviderCall = {
  id: 'helper', run_id: 'run', attempt: 1, state: 'succeeded', purpose: 'compaction',
  requested_model: 'model', requested_effort: 'high', actual_model: 'model',
  actual_provider: 'DeepInfra', usage: { prompt_tokens: 190_000, cost: 0.05 },
}

test('helper-only run never presents helper input as main or claims a main answer', () => {
  const html = renderToStaticMarkup(<MimiRunObservations calls={[helper]} observation={{
    ...observation, main_calls: 0, unknown_cost_calls: 0, main_unknown_cost_calls: 0,
    cost_complete: true, error_code: null,
  }} />)
  expect(html).toContain('Chưa có input main trong receipt')
  expect(html).toContain('Chưa dispatch main mới')
  expect(html).toContain('Helper compact')
  expect(html).toContain('$0.050000')
})

test('run totals explicitly remain incomplete with unknown cost and reused receipts', () => {
  const html = renderToStaticMarkup(<MimiRunObservations calls={[helper]} observation={observation} />)
  expect(html).toContain('chưa phải tổng đầy đủ')
  expect(html).toContain('1 call chưa rõ chi phí')
  expect(html).toContain('không cộng như dispatch trả phí mới')
  expect(html).toContain('provider_refused')
})
