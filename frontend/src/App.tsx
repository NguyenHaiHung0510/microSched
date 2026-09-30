import { ReminderConfirmScreen } from '@/ReminderConfirmScreen'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  Bot,
  CalendarDays,
  ListTodo,
  BookOpen,
  LogOut,
  NotebookPen,
  RefreshCw,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

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
import { cn } from '@/lib/utils'
import { LiveStatus } from '@/LiveStatus'
import HomePage from '@/HomePage'
import { ReminderCenter } from '@/ReminderCenter'
import { MimiControlCenter } from '@/MimiControlCenter'
import { MimiDock, MimiDockButton } from '@/MimiDock'
import { isHomepage, type PublicAuthState } from '@/public-navigation'
import { purgePrivateSurface, saveSessionBootstrap } from '@/lib/public-cache'
import { OutboxStatus } from '@/OutboxStatus'

type SessionResponse = PrivateSessionState & {
  email: string
  signed_in_at: string | null
  expires_at: string
  mimi_available: boolean
  offline_bootstrap?: boolean
  offline_snapshot_at?: number | null
}

async function fetchSession(): Promise<SessionResponse> {
  const session = await apiRequest<SessionResponse>('/api/me')
  await saveSessionBootstrap({ ...session, last_verified: true }).catch(() => {
    window.dispatchEvent(new Event('microsched:offline-unavailable'))
  })
  return session
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

function SignedIn({ session, offline }: { session: SessionResponse; offline: boolean }) {
  const queryClient = useQueryClient()
  // 011c §5.1: exactly one deep-linked screen besides the tab block; every tab
  // keeps the URL "/" and activeScreen stays a useState (tabs do NOT own URLs).
  const location = useLocation()
  const reminderDispatchKey = queryParams(location).get('dispatch') ?? ''
  const isTrackersRoute = location.startsWith('/trackers')
  const [activeScreen, setActiveScreen] = useState<
    'tasks' | 'notes' | 'calendar' | 'tracker' | 'mimi'
  >(() => (isTrackersRoute ? 'tracker' : 'tasks'))
  const [mimiDockOpen, setMimiDockOpen] = useState(false)

  const currentTab = isTrackersRoute ? 'tracker' : activeScreen

  const goToDefaultScreen = useCallback(() => {
    if (location !== '/') {
      navigate('/')
    }
    setActiveScreen('tasks')
  }, [location])

  function selectTab(tab: 'tasks' | 'notes' | 'calendar' | 'tracker' | 'mimi') {
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
    onSuccess: async () => {
      await purgePrivateSurface(queryClient, true)
      window.location.assign('/')
    },
  })

  return (
    <div className={cn(
      'mx-auto grid w-full items-start gap-4',
      mimiDockOpen ? 'max-w-[1920px] xl:grid-cols-[minmax(0,1fr)_minmax(24rem,28rem)]' : currentTab === 'mimi' ? 'max-w-[1920px]' : currentTab === 'calendar' && location === '/' ? 'max-w-[1680px]' : 'max-w-5xl',
    )}>
    <div className="min-w-0 overflow-hidden rounded-xl bg-background shadow-3">
      <header className="flex items-center justify-between gap-4 px-5 pt-5 pb-2 sm:px-6">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1>
          <Button asChild
            data-testid="app-logo-button"
            variant="ghost"
            size="lg"
            className="min-h-11 px-0 text-xl font-extrabold tracking-tight text-primary hover:bg-transparent hover:text-primary text-left focus-visible:ring-2 focus-visible:ring-primary"
            aria-label="Về trang Task mặc định"
          >
            <a href="/" onClick={(event) => {
              if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
              event.preventDefault()
              goToDefaultScreen()
            }}>
              microSched
            </a>
          </Button>
          </h1>
          <p className="text-xs capitalize text-muted-foreground">{todayLabel()}</p>
          {currentTab !== 'calendar' && currentTab !== 'mimi' && !location.startsWith('/subscription') && !location.startsWith('/reminder-confirm') ? (
            <div className="basis-full"><LiveStatus key={currentTab} tab={currentTab} /></div>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {session.mimi_available ? (
            <MimiDockButton open={mimiDockOpen} onToggle={() => setMimiDockOpen((open) => !open)} />
          ) : null}
          <ReminderCenter key={`reminders-${privateScopeVersion}`} />
            {!offline && !session.offline_bootstrap ? <PrivateGate session={session} onVisibilityChange={onPrivateVisibilityChange} /> : null}
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
        <OutboxStatus queryKey={[]} privateUnlocked={Boolean(session.private_until)} />
        <Button asChild variant="link" size="lg" className="mb-2 px-0 text-xs">
          <a href="/home" data-testid="app-homepage-link"><BookOpen aria-hidden="true" />Giới thiệu microSched</a>
        </Button>
        {location.startsWith('/subscription') ? (
          <SubscriptionScreen />
        ) : location.startsWith('/reminder-confirm') ? (
          <ReminderConfirmScreen key={reminderDispatchKey} />
        ) : (
          <>
        <div className="mb-4 grid grid-cols-3 gap-1 sm:flex sm:flex-wrap [&>button]:min-w-0 [&>button]:px-1 [&>button]:text-xs [&>button]:transition-colors sm:[&>button]:px-3 sm:[&>button]:text-sm" role="tablist" aria-label="Chọn nội dung">
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
          {session.mimi_available ? (
            <Button
              role="tab"
              size="lg"
              variant={currentTab === 'mimi' ? 'selected' : 'ghost'}
              aria-selected={currentTab === 'mimi'}
              onClick={() => selectTab('mimi')}
            >
              <Bot data-icon="inline-start" />
              Mimi
            </Button>
          ) : null}
        </div>
        <div role="tabpanel">
          {currentTab === 'tasks' ? <TasksScreen key={`tasks-${privateScopeVersion}`} /> : null}
          {currentTab === 'notes' ? <NotesScreen /> : null}
          {currentTab === 'calendar' ? <CalendarScreen key={`calendar-${privateScopeVersion}`} /> : null}
          {currentTab === 'tracker' ? (
            <TrackerScreen privateUnlocked={Boolean(session.private_until)} />
          ) : null}
          {currentTab === 'mimi' && session.mimi_available ? (
            <MimiControlCenter onOpenDomain={(domain) => selectTab(domain)} />
          ) : null}
        </div>
          </>
        )}
        {logout.isError ? (
          <p className="mt-4 text-sm text-bad">Không thể đăng xuất. Thử lại sau.</p>
        ) : null}
      </div>
    </div>
    {session.mimi_available ? (
      <MimiDock open={mimiDockOpen} onOpenChange={setMimiDockOpen} onOpenTasks={() => selectTab('tasks')} />
    ) : null}
    </div>
  )
}

function App() {
  const location = useLocation()
  const queryClient = useQueryClient()
  const [offline, setOffline] = useState(!navigator.onLine)
  const [sessionExpired, setSessionExpired] = useState(false)
  const [authRejected, setAuthRejected] = useState(false)
  useEffect(() => {
    const update = () => {
      if (!navigator.onLine) {
        queryClient.setQueryData<SessionResponse>(['session'], (old) => old ? { ...old, private_until: null, private_locked_until: null, offline_bootstrap: true } : old)
        void purgePrivateSurface(queryClient)
      }
      setOffline(!navigator.onLine)
    }
    const rejectSession = () => { setAuthRejected(true); void purgePrivateSurface(queryClient, true).then(() => queryClient.invalidateQueries({ queryKey: ['session'] })) }
    const rejectPrivate = () => {
      queryClient.setQueryData<SessionResponse>(['session'], (old) => old ? { ...old, private_until: null } : old)
      void purgePrivateSurface(queryClient)
    }
    window.addEventListener('microsched:unauthenticated', rejectSession)
    window.addEventListener('microsched:private-locked', rejectPrivate)
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    return () => {
      window.removeEventListener('online', update)
      window.removeEventListener('offline', update)
      window.removeEventListener('microsched:unauthenticated', rejectSession)
      window.removeEventListener('microsched:private-locked', rejectPrivate)
    }
  }, [queryClient])
  const session = useQuery({
    queryKey: ['session'],
    queryFn: fetchSession,
    enabled: !authRejected,
    networkMode: 'always',
    // The session has a long TTL. Window focus checks it when returning to the
    // tab; keeping no-poll explicit prevents future defaults from changing it.
    ...NO_POLLING_QUERY_OPTIONS,
    // Being logged out is an answer, not a failure worth retrying.
    retry: (failureCount, error) =>
      !(error instanceof UnauthenticatedError) && failureCount < 2,
  })

  useEffect(() => {
    if (session.error instanceof UnauthenticatedError) {
      void purgePrivateSurface(queryClient, true)
      return
    }
    if (session.data && !session.data.offline_bootstrap && !session.isError) {
      window.dispatchEvent(new Event('microsched:outbox-session-changed'))
    }
  }, [queryClient, session.data, session.dataUpdatedAt, session.error, session.isError])
  useEffect(() => {
    if (!session.data) return
    if (offline && session.data.private_until) {
      queryClient.setQueryData<SessionResponse>(['session'], { ...session.data, private_until: null,
        private_locked_until: null, offline_bootstrap: true }, { updatedAt: 0 })
      void purgePrivateSurface(queryClient)
    }
    const deadline = Date.parse(session.data.expires_at)
    const delay = deadline - Date.now()
    const markExpired = () => setSessionExpired(true)
    if (!Number.isFinite(delay) || delay <= 0) {
      const timer = window.setTimeout(markExpired, 0)
      return () => window.clearTimeout(timer)
    }
    const clearExpired = window.setTimeout(() => setSessionExpired(false), 0)
    let timer = 0
    const schedule = () => {
      const remaining = deadline - Date.now()
      timer = window.setTimeout(() => {
        if (deadline <= Date.now()) markExpired()
        else schedule()
      }, Math.min(2_147_483_647, Math.max(0, remaining)))
    }
    schedule()
    return () => { window.clearTimeout(clearExpired); window.clearTimeout(timer) }
  }, [offline, queryClient, session.data])

  const loggedOut = authRejected || (session.isError && session.error instanceof UnauthenticatedError)
  const publicAuth: PublicAuthState = session.isPending ? 'checking'
    : loggedOut ? 'guest'
      : session.isError ? 'unknown'
        : session.data ? 'signed-in' : 'checking'
  // Public content does not mount protected screens. Explicit /home also stays
  // readable during a session/network check and when the Owner is signed in.
  if (isHomepage(location) || loggedOut) {
    return <HomePage auth={publicAuth} location={location} onRetry={() => void session.refetch()} />
  }

  return (
    <TooltipProvider>
      <main className="min-h-screen bg-muted px-4 py-6 sm:px-6 sm:py-8">
        {/* `aria-live` từng nằm trên chính div này. Nó bọc cả app, nên mọi thay đổi
            bên trong — tick một mục, ghim, đổi bộ lọc — đều có thể bị đọc lên.
            Vùng thông báo phải NHỎ và chỉ chứa thứ đáng thông báo. */}
        <div
          className="mx-auto max-w-[1920px]"
        >
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


          {session.isError && !loggedOut && !session.data ? (
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
          {sessionExpired ? <Card className="mx-auto max-w-lg p-6" role="alert">Cần kết nối để xác thực lại.</Card> : null}
          {session.data && !loggedOut && !sessionExpired ? <>
            {offline || session.data.offline_bootstrap || session.isError ? <p className="mb-3 text-sm text-muted-foreground" role="status">
              {offline || session.isError ? 'Đang ngoại tuyến' : 'Đang xác thực lại'} · dữ liệu lúc {session.data.offline_snapshot_at ? new Date(session.data.offline_snapshot_at).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }) : 'lần kết nối trước'}
            </p> : null}
            <SignedIn key={`${offline}:${session.data.private_until ?? 'locked'}`} session={session.data} offline={offline} />
          </> : null}
        </div>
        <Toaster />
      </main>
    </TooltipProvider>
  )
}

export default App
