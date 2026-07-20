import { useQuery } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'

type HealthResponse = {
  status: string
  version: string
}

async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch('/api/healthz')

  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`)
  }

  return response.json() as Promise<HealthResponse>
}

function App() {
  const health = useQuery({ queryKey: ['healthz'], queryFn: fetchHealth })

  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-6 px-6">
      <div className="space-y-2">
        <p className="text-sm font-medium text-neutral-500">Welcome</p>
        <h1 className="text-4xl font-semibold tracking-tight">microSched</h1>
        <p className="text-neutral-600">Your personal schedule, ready to grow.</p>
      </div>

      <section className="rounded-lg border bg-white p-4 shadow-sm" aria-live="polite">
        <h2 className="font-medium">API health</h2>
        {health.isPending ? <p className="mt-2 text-sm text-neutral-600">Checking…</p> : null}
        {health.data ? (
          <p className="mt-2 text-sm text-neutral-600">
            {health.data.status} · version {health.data.version}
          </p>
        ) : null}
        {health.isError ? (
          <div className="mt-2 flex items-center gap-3">
            <p className="text-sm text-red-700">Unable to reach the API.</p>
            <Button variant="outline" size="sm" onClick={() => void health.refetch()}>
              Try again
            </Button>
          </div>
        ) : null}
      </section>
    </main>
  )
}

export default App
