import { expect, test } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { MimiMessage } from '@/mimi-api'
import { MimiSystemNotice } from './MimiSystemNotice'
import { isVerifiedServerNotice } from './mimi-message-provenance'

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

test('approved notice has Info, collapsed details and full safe prose; no avatar or answer controls', () => {
  const html = renderToStaticMarkup(<MimiSystemNotice message={message} />)
  expect(html).toContain('Hệ thống')
  expect(html).toContain('lucide-info')
  expect(html).toContain(message.content)
  expect(html).toContain('<details')
  expect(html).not.toContain('<details open')
  expect(html).not.toContain('<button')
  expect(html).not.toContain('mimi-answer-avatar')
  expect(html).toContain('provider_terminal')
  expect(renderToStaticMarkup(<MimiSystemNotice message={{ ...message, provenance: undefined }} />)).toBe('')
})
