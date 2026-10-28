import { MimiMetricsTable } from './MimiConversationMetrics'
import { afterEach, expect, test, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MimiContextComposition } from './MimiContextComposition'
import { MimiOperatingPolicyPanel } from './MimiOperatingPolicyPanel'
import { CONTEXT_BUCKETS, lastMeasuredMain, validContextComposition } from './mimi-context-metrics'
import { operatingPolicyErrors, unicodeCodepoints } from './mimi-operating-policy'
import { readMimiComposerDraft, setMimiComposerDraft } from './mimi-selection'
import type { MimiContextComposition as Composition, MimiConversation, MimiProviderCall } from './mimi-api'

afterEach(() => vi.unstubAllGlobals())
const call = (delta: Partial<MimiProviderCall> = {}): MimiProviderCall => ({
  id: 'synthetic-main', run_id: 'synthetic-run', attempt: 1, state: 'succeeded',
  requested_model: 'synthetic/model', requested_effort: 'high', actual_model: 'synthetic/model',
  actual_provider: 'Synthetic Provider', usage: { prompt_tokens: 204000, cached_tokens: 150000 },
  purpose: 'main', paid_dispatch: true, ...delta,
})
const composition = (): Composition => ({ state: 'measured_bytes', total: 8,
  unit: 'bytes', output_reserve: 8192, method: 'serialized_utf8_bytes', for: 'assembled_request_not_next_unsent_request',
  categories: CONTEXT_BUCKETS.map(([id]) => ({ id, value: 1, state: 'measured_bytes' })),
})

test('last main input stays separate from traffic and byte composition in the shared stats', () => {
  const main = call()
  const calls = [main, call({ purpose: 'compaction' }), call({ paid_dispatch: false }),
    call({ actual_model: 'wrong/model' }), call({ actual_provider: null })]
  expect(lastMeasuredMain(calls)).toBe(main)
  const html = renderToStaticMarkup(<MimiMetricsTable conversation={{ provider_calls: calls } as MimiConversation} />)
  expect(html).toContain('204.000')
  expect(html).toContain('400k')
  expect(html).toContain('context hiện tại chưa đo lại')
  expect(html).toContain('Chưa có tổng hợp từ server')
  expect(html).not.toContain('354.000')
  expect(html).not.toContain('Bytes')
})

test('missing usage and malformed bucket counts remain unknown without synthetic live totals', () => {
  const html = renderToStaticMarkup(<MimiMetricsTable conversation={{ provider_calls: [] } as unknown as MimiConversation} />)
  expect(html).not.toContain('204.000')
  expect(validContextComposition(composition())).toBe(true)
  for (const value of [
    { ...composition(), total: 7 },
    { ...composition(), categories: composition().categories!.map(() => ({ id: 'policy', value: 1, state: 'measured_bytes' as const })) },
    { ...composition(), method: 'invented' },
  ]) expect(validContextComposition(value)).toBe(false)
  const chip = renderToStaticMarkup(<MimiContextComposition conversation={{ provider_calls: [] } as unknown as MimiConversation} />)
  expect(chip).toContain('usage chưa xác định')
  expect(chip).toContain('aria-haspopup="dialog"')
})

test('50K codepoints and over-limit draft survive emoji without UTF16 slicing or storage persistence', () => {
  const dispatch = vi.fn()
  vi.stubGlobal('window', { dispatchEvent: dispatch })
  const full = '🌸'.repeat(50000) + 'ệ'
  expect(full.length).toBe(100001)
  expect(unicodeCodepoints(full)).toBe(50001)
  setMimiComposerDraft('synthetic-draft', full)
  expect(readMimiComposerDraft('synthetic-draft')).toBe(full)
  setMimiComposerDraft('synthetic-draft', '')
  expect(readMimiComposerDraft('synthetic-draft')).toBe('')
})

test('config A renders actual loaded revision/manual caps and rejects nonfinite drafts', () => {
  const policy = { revision: 7, input_codepoints: 50000,
    prices: { 'deepseek/deepseek-v4.1-flash': { prompt: '0.36', completion: '1.44' } } }
  expect(operatingPolicyErrors(policy)).toEqual([])
  for (const bad of ['NaN', 'Infinity', '-1', '1000.01', '.000000001']) {
    expect(operatingPolicyErrors({ ...policy, prices: { synthetic: { prompt: bad, completion: '1' } } }).length).toBeGreaterThan(0)
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(['mimi', 'operating-policy'], { policy, applies_to: 'next_unsent_wire' })
  const html = renderToStaticMarkup(<QueryClientProvider client={client}><MimiOperatingPolicyPanel profiles={[]} enabled /></QueryClientProvider>)
  expect(html).toContain('value="50000"')
  expect(html).toContain('value="0.36"')
  expect(html).toContain('value="1.44"')
  expect(html).toContain('không phải báo giá live')
  expect(html).toContain('Kiểm tra thay đổi')
  client.clear()
})


test('old byte/output-reserve composition does not become an estimated current-context count', () => {
  const html = renderToStaticMarkup(<MimiMetricsTable conversation={{ provider_calls: [call({ context_composition: composition() })] } as MimiConversation} />)
  expect(html).toContain('204.000')
  expect(html).not.toContain('8.192')
  expect(html).not.toContain('System policy')
})
