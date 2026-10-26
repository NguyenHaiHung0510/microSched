import { expect, test, vi } from 'vitest'
import { MimiResponseClock } from './mimi-response-timing'
import type { MimiResponseTiming } from './mimi-api'

const response = (patch: Partial<MimiResponseTiming> = {}): MimiResponseTiming => ({ run_id: 'run', target_id: 'answer', source_id: 'submit', phase: 'send', response_kind: 'answer', outcome: 'succeeded', parent_run_id: null, elapsed_ms: null, observation: 'missing', provenance: 'client', ...patch })

test('end uses full monotonic journey including tools/retry/render; wall-clock changes are irrelevant', () => {
  const clock = new MimiResponseClock()
  clock.begin({ conversationId: 'c', sourceId: 'submit', phase: 'send', runId: null, started: 100, hidden: false })
  expect(clock.candidates('c', [response()])).toHaveLength(0)
  clock.bind('c', 'send', 'submit', 'run')
  const candidate = clock.candidates('c', [response()])[0]
  vi.spyOn(Date, 'now').mockReturnValue(-1_000_000)
  clock.complete(candidate.key, candidate.start, candidate.response, 14100, 'visible_paint')
  expect(clock.receipts.get(candidate.key)?.body.elapsed_ms).toBe(14000)
  expect(clock.candidates('c', [response()])).toHaveLength(0)
  vi.restoreAllMocks()
})

test('hidden/offscreen do not fabricate E2E; reload/history has no original start', () => {
  for (const observation of ['hidden', 'offscreen'] as const) {
    const clock = new MimiResponseClock()
    expect(clock.candidates('c', [response()])).toEqual([])
    clock.begin({ conversationId: 'c', sourceId: 'submit', phase: 'send', runId: 'run', started: 100, hidden: false })
    clock.hide()
    const candidate = clock.candidates('c', [response()])[0]
    expect(candidate.start.hidden).toBe(true)
    clock.complete(candidate.key, candidate.start, candidate.response, 200, observation)
    expect(clock.receipts.get(candidate.key)?.body.elapsed_ms).toBeNull()
  }
})

test('pending chunk does not complete; phase and resume identity are exact; failure retains duration', () => {
  const clock = new MimiResponseClock()
  clock.begin({ conversationId: 'c', sourceId: 'submit', phase: 'send', runId: 'run', started: 10, hidden: false })
  expect(clock.candidates('c', [response({ outcome: 'pending' })])).toEqual([])
  expect(clock.candidates('c', [response({ phase: 'confirmation' }), response({ phase: 'resume' })])).toEqual([])
  const candidate = clock.candidates('c', [response({ outcome: 'failed' })])[0]
  clock.complete(candidate.key, candidate.start, candidate.response, 4010, 'visible_paint')
  expect(clock.receipts.get(candidate.key)?.body.elapsed_ms).toBe(4000)
})

test('clock discontinuity never produces a receipt', () => {
  const clock = new MimiResponseClock()
  clock.begin({ conversationId: 'c', sourceId: 'submit', phase: 'send', runId: 'run', started: 100, hidden: false })
  const candidate = clock.candidates('c', [response()])[0]
  for (const now of [NaN, Infinity, 50, 86_400_101]) clock.complete(candidate.key, candidate.start, candidate.response, now, 'visible_paint')
  expect(clock.receipts.size).toBe(0)
})
