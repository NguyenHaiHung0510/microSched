import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'

export const LIVE_REFETCH_MS = 1000

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Keep task views current while a healthy, visible tab is open. A query
      // that is already failing must stop polling: /api/me is DB-backed and a
      // forgotten login tab must not recreate the Neon health-check incident.
      refetchInterval: (query) =>
        query.state.status === 'error' ? false : LIVE_REFETCH_MS,
      // TanStack Query defaults this to false. Hidden tabs therefore stop the
      // interval through the Page Visibility API without a custom listener.
      // Expensive queries can opt out explicitly with `refetchInterval: false`.
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
