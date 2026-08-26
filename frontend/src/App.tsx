import { ReminderConfirmScreen } from '@/ReminderConfirmScreen'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Activity,
  CalendarDays,
  ListTodo,
  LogIn,
  LogOut,
  NotebookPen,
  RefreshCw,
} from 'lucide-react'
import { useCallback, useState } from 'react'

import { apiRequest, UnauthenticatedError } from '@/api'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { CalendarScreen } from '@/CalendarScreen'
import { NotesScreen } from '@/NotesScreen'
import { PrivateGate } from '@/PrivateGate'
import type { PrivateSessionState } from '@/private-gate'
import { navigate, queryParams, useLocation } from '@/lib/route'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'
import { SubscriptionScreen } from '@/SubscriptionScreen'
import { TasksScreen } from '@/TasksScreen'
import { TrackerScreen } from '@/TrackerScreen'

type SessionResponse = PrivateSessionState & {
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
  const location = useLocation()
  // F8: OAuth redirect phải quay về ĐÚNG chỗ người dùng định làm (nhắc thuốc,
  // subscription…) — nếu không, prompt bị nuốt khi session hết hạn. Chỉ gửi
  // pathname+search tương đối, không bao giờ origin (chống open-redirect).
  const returnTo =
    location.startsWith('/') && !location.startsWith('//') ? location : '/'
  const loginHref = `/auth/login?return_to=${encodeURIComponent(returnTo)}`
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
          <a href={loginHref} data-testid="login-link">
            <LogIn data-icon="inline-start" />
            Đăng nhập bằng Google
          </a>
        </Button>
      </Card>
    </div>
  )
}

function SignedIn({ session }: { session: SessionResponse }) {
  // 011c §5.1: exactly one deep-linked screen besides the tab block; every tab
  // keeps the URL "/" and activeScreen stays a useState (tabs do NOT own URLs).
  const location = useLocation()
  const reminderDispatchKey = queryParams(location).get('dispatch') ?? ''
  const isTrackersRoute = location.startsWith('/trackers')
  const [activeScreen, setActiveScreen] = useState<
    'tasks' | 'notes' | 'calendar' | 'tracker'
  >(() => (isTrackersRoute ? 'tracker' : 'tasks'))

  const currentTab = isTrackersRoute ? 'tracker' : activeScreen

  function selectTab(tab: 'tasks' | 'notes' | 'calendar' | 'tracker') {
    if (isTrackersRoute) {
      navigate('/')
    }
    setActiveScreen(tab)
  }

  // A private visibility transition is a local-state boundary as well as a
  // query-cache boundary. Remount the two views that can hold private task
  // rows in dialog/history state after lock, expiry, or unlock.
  const [privateScopeVersion, setPrivateScopeVersion] = useState(0)
  const onPrivateVisibilityChange = useCallback(() => {
    setPrivateScopeVersion((version) => version + 1)
  }, [])
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
        <div className="flex flex-wrap items-center justify-end gap-2">
          <PrivateGate session={session} onVisibilityChange={onPrivateVisibilityChange} />
          <Button
            variant="secondary"
            size="icon-lg"
            className="size-11"
            aria-label="Đăng xuất"
            disabled={logout.isPending}
            onClick={() => logout.mutate()}
          >
            <LogOut />
          </Button>
        </div>
      </header>

      <div className="px-5 pt-3 pb-6 sm:px-6">
        {location.startsWith('/subscription') ? (
          <SubscriptionScreen />
        ) : location.startsWith('/reminder-confirm') ? (
          <ReminderConfirmScreen key={reminderDispatchKey} />
        ) : (
          <>
        <div className="mb-4 flex flex-wrap gap-1" role="tablist" aria-label="Chọn nội dung">
          <Button
            role="tab"
            size="lg"
            variant={currentTab === 'tasks' ? 'selected' : 'ghost'}
            aria-selected={currentTab === 'tasks'}
            onClick={() => selectTab('tasks')}
          >
            <ListTodo data-icon="inline-start" />
            Task
          </Button>
          <Button
            role="tab"
            size="lg"
            variant={currentTab === 'notes' ? 'selected' : 'ghost'}
            aria-selected={currentTab === 'notes'}
            onClick={() => selectTab('notes')}
          >
            <NotebookPen data-icon="inline-start" />
            Ghi chú
          </Button>
          <Button
            role="tab"
            size="lg"
            variant={currentTab === 'calendar' ? 'selected' : 'ghost'}
            aria-selected={currentTab === 'calendar'}
            onClick={() => selectTab('calendar')}
          >
            <CalendarDays data-icon="inline-start" />
            Lịch
          </Button>
          <Button
            role="tab"
            size="lg"
            variant={currentTab === 'tracker' ? 'selected' : 'ghost'}
            aria-selected={currentTab === 'tracker'}
            onClick={() => selectTab('tracker')}
          >
            <Activity data-icon="inline-start" />
            Theo dõi
          </Button>
        </div>
        <div role="tabpanel">
          {currentTab === 'tasks' ? <TasksScreen key={`tasks-${privateScopeVersion}`} /> : null}
          {currentTab === 'notes' ? <NotesScreen /> : null}
          {currentTab === 'calendar' ? <CalendarScreen key={`calendar-${privateScopeVersion}`} /> : null}
          {currentTab === 'tracker' ? (
            <TrackerScreen privateUnlocked={Boolean(session.private_until)} />
          ) : null}
        </div>
          </>
        )}
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
    // The session has a long TTL. Window focus checks it when returning to the
    // tab; keeping no-poll explicit prevents future defaults from changing it.
    ...NO_POLLING_QUERY_OPTIONS,
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
          {session.data && !loggedOut ? <SignedIn session={session.data} /> : null}
        </div>
        <Toaster />
      </main>
    </TooltipProvider>
  )
}

export default App
