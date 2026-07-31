import { useMutation, useQuery } from '@tanstack/react-query'
import { LogIn, LogOut, RefreshCw } from 'lucide-react'

import { apiRequest, UnauthenticatedError } from '@/api'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
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

function todayLabel(): string {
  return new Intl.DateTimeFormat('vi-VN', {
    weekday: 'long',
    day: '2-digit',
    month: '2-digit',
  }).format(new Date())
}

function LoginScreen() {
  return (
    <div className="mx-auto max-w-lg space-y-5 pt-10 sm:pt-20">
      <div className="space-y-1 text-center">
        <h1 className="text-2xl font-extrabold tracking-tight text-primary">
          microSched
        </h1>
        <p className="text-sm text-muted-foreground">
          Lên việc, chia checklist, hoàn thành từng bước.
        </p>
      </div>
      <Card className="gap-5 rounded-lg bg-card p-6 shadow-2 ring-0">
        <div className="space-y-1">
          <h2 className="text-lg font-bold">Cần đăng nhập</h2>
          <p className="text-sm text-muted-foreground">
            microSched là dự án cá nhân, chỉ mở cho tài khoản của chủ sở hữu.
          </p>
        </div>
        {/* A real link, not fetch: the OAuth handshake needs a full page navigation. */}
        <Button asChild size="lg">
          <a href="/auth/login">
            <LogIn data-icon="inline-start" />
            Đăng nhập bằng Google
          </a>
        </Button>
      </Card>
    </div>
  )
}

function SignedIn() {
  const logout = useMutation({
    mutationFn: postLogout,
    // Full navigation, not cache surgery. Logging in is already a real page load
    // (the OAuth redirect), so logging out being one too keeps the two halves
    // symmetric - and it makes the server the single source of truth instead of
    // resting on how the query cache reacts to being invalidated or removed.
    onSuccess: () => window.location.assign('/'),
  })

  return (
    <div className="overflow-hidden rounded-xl bg-background shadow-3">
      <header className="flex items-center justify-between gap-4 px-5 pt-5 pb-2 sm:px-6">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1 className="text-xl font-extrabold tracking-tight text-primary">
            microSched
          </h1>
          <p className="text-xs capitalize text-muted-foreground">{todayLabel()}</p>
        </div>
        <Button
          variant="secondary"
          size="icon-lg"
          aria-label="Đăng xuất"
          disabled={logout.isPending}
          onClick={() => logout.mutate()}
        >
          <LogOut />
        </Button>
      </header>

      <div className="px-5 pt-3 pb-6 sm:px-6">
        <TasksScreen />
        {logout.isError ? (
          <p className="mt-4 text-sm text-bad">Không thể đăng xuất. Thử lại sau.</p>
        ) : null}
      </div>
    </div>
  )
}

function App() {
  const session = useQuery({
    queryKey: ['session'],
    queryFn: fetchSession,
    // The session has a long TTL. Window focus already checks it when returning
    // to the tab, so it must opt out of the live task polling default.
    refetchInterval: false,
    // Being logged out is an answer, not a failure worth retrying.
    retry: (failureCount, error) =>
      !(error instanceof UnauthenticatedError) && failureCount < 2,
  })

  const loggedOut = session.isError && session.error instanceof UnauthenticatedError

  return (
    <TooltipProvider>
      <main className="min-h-screen bg-muted px-4 py-6 sm:px-6 sm:py-8">
        {/* `aria-live` từng nằm trên chính div này. Nó bọc cả app, nên mọi thay đổi
            bên trong — tick một mục, ghim, đổi bộ lọc — đều có thể bị đọc lên.
            Vùng thông báo phải NHỎ và chỉ chứa thứ đáng thông báo. */}
        <div className="mx-auto max-w-5xl">
          {session.isPending ? (
            <Card
              className="mx-auto max-w-lg gap-4 rounded-lg bg-card p-6 shadow-2 ring-0"
              role="status"
            >
              <h1 className="text-2xl font-extrabold tracking-tight text-primary">
                microSched
              </h1>
              <p className="text-sm text-muted-foreground">
                Đang kiểm tra phiên đăng nhập…
              </p>
            </Card>
          ) : null}

          {loggedOut ? <LoginScreen /> : null}

          {session.isError && !loggedOut ? (
            <Card
              className="mx-auto max-w-lg gap-4 rounded-lg bg-card p-6 shadow-2 ring-0"
              role="alert"
            >
              <div className="space-y-1">
                <h1 className="text-2xl font-extrabold tracking-tight text-primary">
                  microSched
                </h1>
                <p className="text-sm text-bad">Không kết nối được API.</p>
              </div>
              <Button variant="outline" size="lg" onClick={() => void session.refetch()}>
                <RefreshCw data-icon="inline-start" />
                Thử lại
              </Button>
            </Card>
          ) : null}

          {/* Guard on loggedOut too: stale data must never show beside the login screen. */}
          {session.data && !loggedOut ? <SignedIn /> : null}
        </div>
        <Toaster />
      </main>
    </TooltipProvider>
  )
}

export default App
