import { expect, test, vi } from 'vitest'
import { ApiError } from '@/api'
import { commitOutcomeMessage } from './acknowledgement'
import { supplementIntent, type SupplementDraft } from './mimi-positive-supplement'
import { saveMimiFeedback } from './mimi-api'

test('commit-unknown503 keeps original feedback intent/body/target and never retries automatically', async () => {
  const bodies: unknown[] = []
  vi.stubGlobal('fetch', vi.fn(async (_path: string, init: RequestInit) => {
    bodies.push(JSON.parse(String(init.body)))
    return new Response(JSON.stringify({ detail: 'mimi_feedback_commit_unknown' }), { status: 503 })
  }))
  const draft: SupplementDraft = { text: 'Góp ý ban đầu', expected: 'Kết quả ban đầu', reasons: [], revision: 1, intent: null, savedRevision: null }
  const intent = supplementIntent(draft, 'conversation', 'target', 'original-key')!
  let error: unknown
  try { await saveMimiFeedback(intent.conversationId, { target_type: 'turn', target_id: intent.targetId }, intent.comment, intent.expected ?? '', intent.clientId) } catch (caught) { error = caught }
  expect(error).toBeInstanceOf(ApiError)
  expect(commitOutcomeMessage(error)).toContain('Chưa xác định')
  expect(commitOutcomeMessage(error)).not.toContain('chưa lưu')
  expect(bodies).toHaveLength(1)
  expect(supplementIntent({ ...draft, text: 'Bản sửa mới', revision: 2, intent }, 'other', 'other', 'new-key')).toBe(intent)
  expect(bodies[0]).toMatchObject({ client_id: 'original-key', target_id: 'target', expected: 'Kết quả ban đầu' })
  vi.unstubAllGlobals()
})

test('only the six scoped commit losses get uncertainty wording', () => {
  for (const detail of ['mimi_response_timing_commit_unknown', 'mimi_feedback_commit_unknown', 'note_move_to_top_commit_unknown', 'history_handled_commit_unknown', 'history_batch_prepare_commit_unknown', 'history_batch_commit_unknown']) expect(commitOutcomeMessage(new ApiError(503, detail))).toContain('yêu cầu cũ')
  expect(commitOutcomeMessage(new ApiError(409, 'stale'))).toBeNull()
})
