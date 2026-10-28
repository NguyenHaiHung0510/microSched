import { afterEach, expect, test, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MimiScreen } from './MimiScreen'
import type { MimiConversation } from './mimi-api'

afterEach(() => vi.unstubAllGlobals())

for (const variant of ['workspace', 'dock'] as const) {
  test(`${variant}: activity replaces empty welcome before canonical first message arrives`, () => {
    vi.stubGlobal('navigator', { onLine: true })
    vi.stubGlobal('document', { hidden: false })
    const client = new QueryClient({ defaultOptions: { queries: { enabled: false, retry: false } } })
    const conversation: MimiConversation = {
      id: 'synthetic-r1', sensitivity: 'standard', generation: 1,
      messages: [], runs: [], change_sets: [], receipts: [], events: [], feedback: [],
    }
    const render = () => renderToStaticMarkup(<QueryClientProvider client={client}>
      <MimiScreen onOpenTasks={() => {}} conversationId={conversation.id} variant={variant} />
    </QueryClientProvider>)
    client.setQueryData(['mimi', 'conversation', conversation.id], conversation)
    const idle = render()
    expect(idle).toContain('data-testid="mimi-welcome"')
    expect(idle).toContain('mimi-transcript-empty')
    expect(idle).not.toContain('data-testid="mimi-pending-answer"')
    client.setQueryData(['mimi', 'conversation', conversation.id], {
      ...conversation,
      runs: [{ id: 'synthetic-run', generation: 1, state: 'running', provider_outcome: null,
        deadline: '2026-11-02T00:15:00Z', error_code: null,
        created_at: '2026-11-02T00:00:00Z', completed_at: null }],
    })
    const active = render()
    expect(active).toContain('data-testid="mimi-pending-answer"')
    expect(active).toContain('data-testid="mimi-progress"')
    expect(active).not.toContain('data-testid="mimi-welcome"')
    expect(active).not.toContain('mimi-transcript-empty')
    client.clear()
  })
}
