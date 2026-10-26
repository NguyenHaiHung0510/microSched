import { expect, test } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MimiPositiveSupplement } from './MimiPositiveSupplement'
import { acknowledgeSupplement, supplementIntent, verifySupplementAck, hasUnsentSupplement, type SupplementDraft } from './mimi-positive-supplement'

const draft = (patch: Partial<SupplementDraft> = {}): SupplementDraft => ({ text: '', reasons: [], revision: 1, intent: null, savedRevision: null, ...patch })

test('empty does not submit; reasons-only is explicit and each new intent gets its own key', () => {
  expect(supplementIntent(draft(), 'c', 'm', 'key')).toBeNull()
  const first = supplementIntent(draft({ reasons: ['Đúng ý'] }), 'c', 'm', 'key1')!
  expect(first.comment).toContain('Lý do: Đúng ý.')
  expect(first.clientId).toBe('key1')
  const acknowledged = acknowledgeSupplement(draft({ reasons: ['Đúng ý'], intent: first }), first)
  expect(acknowledged.intent).toBeNull()
  expect(acknowledged.reasons).toEqual([])
  expect(supplementIntent({ ...acknowledged, text: 'Thêm chi tiết' }, 'c', 'm', 'key2')!.clientId).toBe('key2')
})

test('unknown retry keeps original key/body/target despite edits; late ACK preserves newer draft', () => {
  const first = supplementIntent(draft({ text: 'Ban đầu', expected: 'Kết quả đầu' }), 'c1', 'm1', 'key1')!
  const edited = draft({ text: 'Đã sửa', expected: 'Kết quả mới', revision: 2, intent: first })
  expect(supplementIntent(edited, 'c2', 'm2', 'key2')).toBe(first)
  const after = acknowledgeSupplement(edited, first)
  expect(after.text).toBe('Đã sửa')
  expect(after.expected).toBe('Kết quả mới')
  expect(first.expected).toBe('Kết quả đầu')
  expect(after.intent).toBeNull()
  expect(after.savedRevision).toBeNull()
  const other = draft({ text: 'Target khác' })
  expect(acknowledgeSupplement(other, first)).toBe(other)
})

test('both detail and expected accept8000 Unicode codepoints without truncation', () => {
  const text = '🌸'.repeat(7999) + 'ệ'
  const intent = supplementIntent(draft({ text, expected: text }), 'c', 'm', 'key')!
  expect(intent.comment).toContain(text)
  expect(intent.expected).toBe(text)
  expect(supplementIntent(draft({ text: text + 'x' }), 'c', 'm', 'key')).toBeNull()
  expect(supplementIntent(draft({ text, expected: text + 'x' }), 'c', 'm', 'key')).toBeNull()
  expect(supplementIntent(draft({ expected: text }), 'c', 'm', 'key')?.expected).toBe(text)
})

test('expected-only memory draft blocks automatic PWA reload until acknowledged', () => {
  const pending = draft({ expected: 'Chỉ nhập kết quả mong đợi' })
  expect(hasUnsentSupplement(pending)).toBe(true)
  const intent = supplementIntent(pending, 'c', 'm', 'key')!
  expect(hasUnsentSupplement(acknowledgeSupplement({ ...pending, intent }, intent))).toBe(false)
  expect(hasUnsentSupplement(undefined)).toBe(false)
})

test('rendered form names explicit submit and separate submission without automatic POST', () => {
  const client = new QueryClient()
  const html = renderToStaticMarkup(<QueryClientProvider client={client}><MimiPositiveSupplement conversationId="c" targetId="m" /></QueryClientProvider>)
  expect(html).toContain('Gửi bổ sung')
  expect(html).toContain('Chỉ gửi khi bạn bấm Gửi bổ sung.')
  expect(html).toContain('0/8.000')
  expect(html).not.toContain('maxlength')
  expect(html).toContain('disabled')
  client.clear()
})


test('ACK guard rejects deliberately wrong identity then accepts restored original receipt', () => {
  const intent = supplementIntent(draft({ text: 'Chi tiết' }), 'c1', 'm1', 'key1')!
  const receipt = { id: 'receipt', client_id: 'key1', target_type: 'turn', target_id: 'm1', state: 'saved', unresolved: false, created_at: '2026-10-18T00:00:00Z' }
  expect(() => verifySupplementAck({ ...receipt, target_id: 'm2' }, intent)).toThrow('target mismatch')
  expect(() => verifySupplementAck({ ...receipt, client_id: 'key2' }, intent)).toThrow('target mismatch')
  expect(verifySupplementAck(receipt, intent)).toBe(receipt)
})
