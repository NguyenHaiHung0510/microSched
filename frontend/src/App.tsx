import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'

type SessionResponse = {
  email: string
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

async function postLogout(): Promise<void> {
  const response = await fetch('/auth/logout', {
    method: 'POST',
    credentials: 'same-origin',
  })

  if (!response.ok) {
    throw new Error(`Logout failed with status ${response.status}`)
  }
}

function LoginScreen() {
  return (
    <section className="space-y-4 rounded-lg border bg-white p-6 shadow-sm">
      <div className="space-y-1">
        <h2 className="font-medium">Cần đăng nhập</h2>
        <p className="text-sm text-neutral-600">microSched chỉ mở cho tài khoản của chủ sở hữu.</p>
      </div>
      {/* A real link, not fetch: the OAuth handshake needs a full page navigation. */}
      <Button asChild>
        <a href="/auth/login">Đăng nhập bằng Google</a>
      </Button>
    </section>
  )
}

function App() {
  const queryClient = useQueryClient()
  const session = useQuery({
    queryKey: ['session'],
    queryFn: fetchSession,
    // Being logged out is an answer, not a failure worth retrying.
    retry: (failureCount, error) =>
      !(error instanceof UnauthenticatedError) && failureCount < 2,
  })
  const logout = useMutation({
    mutationFn: postLogout,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['session'] }),
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

        {session.data ? (
          <section className="flex items-center justify-between gap-4 rounded-lg border bg-white p-4 shadow-sm">
            <div>
              <h2 className="font-medium">Đã đăng nhập</h2>
              <p className="mt-1 text-sm text-neutral-600">{session.data.email}</p>
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={logout.isPending}
              onClick={() => logout.mutate()}
            >
              Đăng xuất
            </Button>
          </section>
        ) : null}
      </div>
    </main>
  )
}

export default App
