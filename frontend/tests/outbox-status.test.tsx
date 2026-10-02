import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { DomainOutboxState } from '@/lib/use-domain-outbox'
import type { OutboxRow } from '@/lib/outbox-db'
const snapshot = vi.hoisted(() => ({ state: {} as DomainOutboxState }))
vi.mock('@/lib/use-domain-outbox', () => ({ useDomainOutbox: () => snapshot.state }))
import { OutboxEntityStatus, OutboxStatus } from '@/OutboxStatus'
const failedRow = { operation_id: 1, operation_kind: 'task.update', entity_id: 'private-task', parent_id: null, requires_private: true, body: null, state: 'failed', last_error_code: 'HTTP_422' } as OutboxRow
function render(element: React.ReactNode, privateUntil: string | null = null) {
  const client = new QueryClient()
  client.setQueryData(['session'], { private_until: privateUntil })
  return renderToStaticMarkup(<QueryClientProvider client={client}>{element}</QueryClientProvider>)
}
beforeEach(() => {
  snapshot.state = { rows: [failedRow], pendingCount: 0, failedCount: 1, unavailable: false, webLocksUnavailable: false, readError: false }
  vi.stubGlobal('navigator', { onLine: true })
})
describe('queue state trust and private status masking', () => {
  it('hides stale rows and destructive controls when the durable read fails', () => {
    snapshot.state.readError = true
    expect(render(<OutboxStatus />)).not.toContain('outbox-indicator')
    expect(render(<OutboxStatus />)).toContain('Chưa đọc được trạng thái hàng đợi')
  })
  it('a private entity flag cannot authorize revealing its failed-write reason', () => {
    const html = render(<OutboxEntityStatus entityId="private-task" />)
    expect(html).toContain('Nội dung đang được ẩn')
    expect(html).not.toContain('Dữ liệu không vượt qua')
  })
  it('reveals the failure reason only with a live verified unlock', () => {
    const html = render(<OutboxEntityStatus entityId="private-task" />, new Date(Date.now() + 60_000).toISOString())
    expect(html).toContain('Dữ liệu không vượt qua kiểm tra nghiệp vụ')
  })
  it('keeps the approved global-only pending indicator instead of adding badges to every entity', () => {
    snapshot.state.rows = [{ ...failedRow, state: 'private_hold' }]
    expect(render(<OutboxEntityStatus entityId="private-task" />)).toBe('')
  })
})
