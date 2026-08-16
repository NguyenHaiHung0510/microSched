import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'
import { APP_QUERY_DEFAULTS } from './query-polling.ts'

const queryClient = new QueryClient({
  defaultOptions: {
    // Polling is opt-in per query family. Mount/focus refresh stays on, while
    // hidden/background intervals stay off through TanStack's focus manager.
    queries: APP_QUERY_DEFAULTS,
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
