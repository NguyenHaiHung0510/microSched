import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'
import { APP_QUERY_DEFAULTS } from './query-polling.ts'
import { initializePublicPersistence, loadSessionBootstrap, publicSnapshotTimestamp } from './lib/public-cache'
import { replayPendingOverlays } from './lib/outbox-adapters'
import { startOutboxCoordinator } from './lib/outbox-coordinator'

const queryClient = new QueryClient({
  defaultOptions: {
    // Polling is opt-in per query family. Mount/focus refresh stays on, while
    // hidden/background intervals stay off through TanStack's focus manager.
    queries: APP_QUERY_DEFAULTS,
  },
})

async function startApp() {
  await initializePublicPersistence(queryClient)
  const bootstrap = await loadSessionBootstrap()
  if (bootstrap) queryClient.setQueryData(['session'], {
    email: bootstrap.email, signed_in_at: bootstrap.signed_in_at, expires_at: bootstrap.expires_at,
    private_until: null, private_locked_until: null, pin_is_set: false, pin_is_bootstrap: false,
    mimi_available: false, offline_bootstrap: true, offline_snapshot_at: await publicSnapshotTimestamp(),
  }, { updatedAt: 0 })
  try { await replayPendingOverlays(queryClient) } catch { window.dispatchEvent(new Event('microsched:outbox-reconcile-unavailable')) }
  try {
    const channel = new BroadcastChannel('microsched-outbox-events')
    channel.onmessage = () => {
      window.dispatchEvent(new Event('microsched:outbox-changed'))
      void replayPendingOverlays(queryClient).then(() => window.dispatchEvent(new Event('microsched:outbox-flush-requested'))).catch(() => window.dispatchEvent(new Event('microsched:outbox-reconcile-unavailable')))
    }
  } catch { /* Browsers without BroadcastChannel retain IndexedDB and local observation. */ }
  startOutboxCoordinator(queryClient)
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </StrictMode>,
  )
}
void startApp()
