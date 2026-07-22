import { useMutation, useQuery } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'

type SessionResponse = {
  email: string
  signed_in_at: string | null
  expires_at: string
}

type HealthResponse = {
  status: string
  version: string
  db: string
}

/** Raised only for a 401 so the UI can tell "logged out" from "API is broken". */
class UnauthenticatedError extends Error {}

async function fetchSession(): Promise<SessionResponse> {
  const response = await fetch('/api/me', { credentials: 'same-origin' })

  if (response.status === 401) {
    throw new UnauthenticatedError('No active session')
  }

  if (!response.ok) {
    throw new Error(`Session check failed with status ${response.status}`)
  }

  return response.json() as Promise<SessionResponse>
}

async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch('/api/healthz', { credentials: 'same-origin' })

  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`)
  }

  return response.json() as Promise<HealthResponse>
}

async function postLogout(): Promise<void> {
  const response = await fetch('/auth/logout', {
    method: 'POST',
    credentials: 'same-origin',
  })

  if (!response.ok) {
    throw new Error(`Logout failed with status ${response.status}`)
  }
}

function greeting(): string {
  const hour = new Date().getHours()

  if (hour < 11) return 'Chào buổi sáng'
  if (hour < 14) return 'Chào buổi trưa'
  if (hour < 18) return 'Chào buổi chiều'
  return 'Chào buổi tối'
}

function formatDate(value: string | null): string {
  if (!value) return '—'

  return new Date(value).toLocaleString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-neutral-500">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium tabular-nums">{value}</dd>
    </div>
  )
}

function LoginScreen() {
  return (
    <section className="space-y-4 rounded-lg border bg-white p-6 shadow-sm">
      <div className="space-y-1">
        <h2 className="font-medium">Cần đăng nhập</h2>
        <p className="text-sm text-neutral-600">
          microSched là dự án cá nhân, chỉ mở cho tài khoản của chủ sở hữu.
        </p>
      </div>
      {/* A real link, not fetch: the OAuth handshake needs a full page navigation. */}
      <Button asChild>
        <a href="/auth/login">Đăng nhập bằng Google</a>
      </Button>
    </section>
  )
}

function SignedIn({ session }: { session: SessionResponse }) {
  const health = useQuery({ queryKey: ['healthz'], queryFn: fetchHealth })
  const logout = useMutation({
    mutationFn: postLogout,
    // Full navigation, not cache surgery. Logging in is already a real page load
    // (the OAuth redirect), so logging out being one too keeps the two halves
    // symmetric - and it makes the server the single source of truth instead of
    // resting on how the query cache reacts to being invalidated or removed.
    onSuccess: () => window.location.assign('/'),
  })

  return (
    <section className="space-y-5 rounded-lg border bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-medium">{greeting()} 👋</h2>
          <p className="mt-1 text-sm text-neutral-600">{session.email}</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={logout.isPending}
          onClick={() => logout.mutate()}
        >
          {logout.isPending ? 'Đang thoát…' : 'Đăng xuất'}
        </Button>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 border-t pt-4">
        <Stat label="Đăng nhập lúc" value={formatDate(session.signed_in_at)} />
        <Stat label="Phiên hết hạn" value={formatDate(session.expires_at)} />
        <Stat label="Phiên bản" value={health.data?.version ?? '…'} />
        <Stat
          label="Cơ sở dữ liệu"
          value={health.data ? (health.data.db === 'up' ? 'kết nối được' : 'mất kết nối') : '…'}
        />
      </dl>
    </section>
  )
}

function App() {
  const session = useQuery({
    queryKey: ['session'],
    queryFn: fetchSession,
    // Being logged out is an answer, not a failure worth retrying.
    retry: (failureCount, error) => !(error instanceof UnauthenticatedError) && failureCount < 2,
  })

  const loggedOut = session.isError && session.error instanceof UnauthenticatedError

  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-6 px-6">
      <div className="space-y-2">
        <p className="text-sm font-medium text-neutral-500">Welcome</p>
        <h1 className="text-4xl font-semibold tracking-tight">microSched</h1>
        <p className="text-neutral-600">Your personal schedule, ready to grow.</p>
      </div>

      <div aria-live="polite">
        {session.isPending ? (
          <p className="text-sm text-neutral-600">Đang kiểm tra phiên đăng nhập…</p>
        ) : null}

        {loggedOut ? <LoginScreen /> : null}

        {session.isError && !loggedOut ? (
          <div className="flex items-center gap-3">
            <p className="text-sm text-red-700">Không kết nối được API.</p>
            <Button variant="outline" size="sm" onClick={() => void session.refetch()}>
              Thử lại
            </Button>
          </div>
        ) : null}

        {/* Guard on loggedOut too: stale data must never show beside the login screen. */}
        {session.data && !loggedOut ? <SignedIn session={session.data} /> : null}
      </div>
    </main>
  )
}

export default App
