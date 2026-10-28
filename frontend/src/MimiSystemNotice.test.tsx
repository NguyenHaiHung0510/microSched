import { expect, test } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { MimiMessage } from '@/mimi-api'
import { MimiSystemNotice } from './MimiSystemNotice'
import { isVerifiedServerNotice, systemNoticeText } from './mimi-message-provenance'

const message: MimiMessage = { id: 'message75', run_id: 'run75', client_id: null, sequence: 4, role: 'assistant', content: 'Route hiện tại không đáp ứng contract.', created_at: '2026-10-09T05:00:00Z', provenance: { origin: 'server_notice', producer_code: 'provider_terminal', version: 1, event_sequence: 7, source: 'server_verified' } }

test('identical prose is a system notice only with explicit verified server origin', () => {
  expect(isVerifiedServerNotice(message)).toBe(true)
  expect(isVerifiedServerNotice({ ...message, provenance: { ...message.provenance!, origin: 'model_answer', producer_code: 'provider_text' } })).toBe(false)
  expect(isVerifiedServerNotice({ ...message, provenance: undefined })).toBe(false)
  expect(isVerifiedServerNotice({ ...message, provenance: { origin: 'unknown', producer_code: null, version: null, event_sequence: null, source: 'absent_or_unverified' } })).toBe(false)
})

test('malformed/unverified metadata and user messages cannot gain system presentation', () => {
  for (const patch of [{ source: 'absent_or_unverified' }, { version: 2 }, { producer_code: 'future_unknown' }, { event_sequence: 0 }, { event_sequence: 1.5 }]) {
    expect(isVerifiedServerNotice({ ...message, provenance: { ...message.provenance!, ...patch } as MimiMessage['provenance'] })).toBe(false)
  }
  expect(isVerifiedServerNotice({ ...message, run_id: null })).toBe(false)
  expect(isVerifiedServerNotice({ ...message, role: 'user' })).toBe(false)
})

test('approved notice has Info, collapsed details and full safe prose without a model avatar', () => {
  const html = renderToStaticMarkup(<MimiSystemNotice message={message} />)
  expect(html).toContain('Hệ thống')
  expect(html).toContain('lucide-info')
  expect(html).toContain(message.content)
  expect(html).toContain('<details')
  expect(html).not.toContain('<details open')
  expect(html).toContain('Sao chép trạng thái hệ thống 4')
  expect(html).not.toContain('mimi-answer-avatar')
  expect(html).toContain('provider_terminal')
  expect(renderToStaticMarkup(<MimiSystemNotice message={{ ...message, provenance: undefined }} />)).toBe('')
})


test('server loop stop offers explicit system feedback on the same verified message', () => {
  const stopped = { ...message, provenance: { ...message.provenance!, producer_code: 'agent_loop_stop' } }
  expect(isVerifiedServerNotice(stopped)).toBe(true)
  const html = renderToStaticMarkup(<MimiSystemNotice message={stopped} onFeedback={() => {}} />)
  expect(html).toContain('Hữu ích · trạng thái hệ thống 4')
  expect(html).toContain('Chưa tốt · trạng thái hệ thống 4')
  expect(html.indexOf('Sao chép trạng thái')).toBeLessThan(html.indexOf('Hữu ích ·'))
  expect(html.indexOf('Hữu ích ·')).toBeLessThan(html.indexOf('Chưa tốt ·'))
})

test('preview notice changes only known verified server voice and retains pending semantics', () => {
  const preview = { ...message, content: 'Mình đã đóng băng phương án cho 2 Task. Chưa áp dụng; hãy kiểm tra thay đổi và xác nhận.', provenance: { ...message.provenance!, producer_code: 'preview_prepared' } }
  expect(systemNoticeText(preview)).toBe('Đã chuẩn bị phương án cho 2 Task. Chưa áp dụng; hãy kiểm tra thay đổi và xác nhận.')
  expect(systemNoticeText({ ...preview, provenance: undefined })).toBe(preview.content)
  const html = renderToStaticMarkup(<MimiSystemNotice message={preview} feedbackPending onFeedback={() => {}} />)
  expect(html).toContain('Chưa áp dụng')
  expect(html.match(/ disabled=""/g)).toHaveLength(2)
})
