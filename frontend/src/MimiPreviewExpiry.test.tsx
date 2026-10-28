import { expect, test, vi, afterEach } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { ChangeSetPreview } from './MimiScreen'
import type { MimiChangeSet } from './mimi-api'

afterEach(() => vi.restoreAllMocks())
function preview(expires: string): MimiChangeSet {
  return { id: 'preview', run_id: 'run', state: 'pending', digest: 'digest', nonce: 'nonce', expires_at: expires,
    policy_version: 'v1', operation: { tool: 'task.create.v1', args: {
      id: 'task', title: 'Chuẩn bị demo', body_md: 'Nội dung', status: 'open', priority: 'p2',
      due_precision: 'none', due_on: null, due_at: null, is_private: false, items: ['Kiểm tra'],
    } } } as MimiChangeSet
}
test('expired preview disables every obsolete action and gives a next step', () => {
  vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-10-02T16:00:00Z'))
  const html = renderToStaticMarkup(<ChangeSetPreview changeSet={preview('2026-10-02T15:59:59Z')} pending={false} error={null} onDecision={() => {}} onRevise={() => {}} />)
  expect(html).toContain('Preview đã hết hạn')
  expect(html).toContain('Gửi yêu cầu mới')
  expect(html.match(/<button[^>]*disabled=""/g)).toHaveLength(3)
})
test('fresh preview keeps the explicit decisions usable until the expiry boundary', () => {
  vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-10-02T16:00:00Z'))
  const html = renderToStaticMarkup(<ChangeSetPreview changeSet={preview('2026-10-02T16:00:01Z')} pending={false} error={null} onDecision={() => {}} onRevise={() => {}} />)
  expect(html).not.toContain('Preview đã hết hạn')
  expect(html.match(/<button[^>]*disabled=""/g) ?? []).toHaveLength(0)
})
