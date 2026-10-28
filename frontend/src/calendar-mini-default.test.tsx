import { afterEach, expect, test, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CalendarScrollView } from './CalendarScrollView'

afterEach(() => vi.unstubAllGlobals())
test('desktop month calendar renders the mini-calendar collapsed and keeps its accessible open toggle', () => {
  vi.stubGlobal('window', { matchMedia: () => ({ matches: true }) })
  vi.stubGlobal('localStorage', { getItem: () => null })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  try {
    const html = renderToStaticMarkup(<QueryClientProvider client={client}><CalendarScrollView /></QueryClientProvider>)
    expect(html).toMatch(/data-testid="calendar-toggle-sidebar"[^>]*aria-expanded="false"/)
    expect(html).toContain('Hiện lịch nhỏ')
    expect(html).not.toContain('data-testid="calendar-mininav"')
    expect(html).toContain('data-testid="calendar-scroll-container"')
  } finally { client.clear() }
})
