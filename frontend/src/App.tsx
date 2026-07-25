import { useMutation, useQuery } from '@tanstack/react-query'

import { apiRequest, UnauthenticatedError } from '@/api'
import { Button } from '@/components/ui/button'
import { TasksScreen } from '@/TasksScreen'

type SessionResponse = {
  email: string
  signed_in_at: string | null
  expires_at: string
}

async function fetchSession(): Promise<SessionResponse> {
  return apiRequest<SessionResponse>('/api/me')
}

async function postLogout(): Promise<void> {
  await apiRequest<void>('/auth/logout', {
    method: 'POST',
  })
}

function greeting(): string {
  const hour = new Date().getHours()

  if (hour < 11) return 'Chào buổi sáng'
  if (hour < 14) return 'Chào buổi trưa'
  if (hour < 18) return 'Chào buổi chiều'
  return 'Chào buổi tối'
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
  const logout = useMutation({
    mutationFn: postLogout,
    // Full navigation, not cache surgery. Logging in is already a real page load
    // (the OAuth redirect), so logging out being one too keeps the two halves
    // symmetric - and it makes the server the single source of truth instead of
    // resting on how the query cache reacts to being invalidated or removed.
    onSuccess: () => window.location.assign('/'),
  })

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4">
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
      </header>
      <TasksScreen />
    </div>
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
    <main className="mx-auto min-h-screen max-w-3xl space-y-6 px-4 py-10 sm:px-6">
      <div className="space-y-2">
        <p className="text-sm font-medium text-neutral-500">Task workspace</p>
        <h1 className="text-4xl font-semibold tracking-tight">microSched</h1>
        <p className="text-neutral-600">Lên việc, chia checklist, hoàn thành từng bước.</p>
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
