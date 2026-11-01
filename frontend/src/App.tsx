import { OutboxPanel, OfflineCoverage, DerivedPendingNotice } from '@/OutboxPanel'
import { useOutbox } from '@/outbox/view'
import { PwaUpdates } from '@/PwaUpdates'
import { sessionRequest, logoutBoundary } from '@/outbox/core'
import { ReminderConfirmScreen } from '@/ReminderConfirmScreen'
import { useMutation, useQuery } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { apiRequest, UnauthenticatedError } from '@/api'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { DomainNavigation, ApplicationMenu } from '@/AppNavigation'
import type { AppScreen } from '@/app-navigation'
import { hasUnsavedFormChanges } from '@/draft-baselines'
import { Card } from '@/components/ui/card'
import { Toaster } from '@/components/ui/sonner'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { MimiAvatar } from '@/components/brand'
import { acceptsMimiShortcut, focusMimiSurface } from '@/mimi-quick-access'
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
import { MimiDock } from '@/MimiDock'
import { isHomepage, type PublicAuthState } from '@/public-navigation'
import { resolveMimiAttention } from '@/mimi-api'
import { selectMimiConversation } from '@/mimi-selection'

type SessionResponse = PrivateSessionState & {
  email: string
  signed_in_at: string | null
  expires_at: string
  mimi_available: boolean
}

async function fetchSession(): Promise<SessionResponse> {
  return sessionRequest()
}

async function postLogout(): Promise<void> {
  await logoutBoundary()
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

function SignedIn({ session }: { session: SessionResponse }) {
  const outboxState = useOutbox()
  // 011c §5.1: exactly one deep-linked screen besides the tab block; every tab
  // keeps the URL "/" and activeScreen stays a useState (tabs do NOT own URLs).
  const location = useLocation()
  const reminderDispatchKey = queryParams(location).get('dispatch') ?? ''
  const isTrackersRoute = location.startsWith('/trackers')
  const [activeScreen, setActiveScreen] = useState<
    'tasks' | 'notes' | 'calendar' | 'tracker' | 'mimi'
  >(() => (isTrackersRoute ? 'tracker' : 'tasks'))
  const [mimiDockOpen, setMimiDockOpen] = useState(false)
  const [mimiDockWidth, setMimiDockWidth] = useState(400)
  const [mimiConfigurationOpen, setMimiConfigurationOpen] = useState(false)

  const isMimiRoute = location.split('?')[0] === '/mimi'
  const attentionLocator = isMimiRoute ? queryParams(location).get('attention') : null
  const attentionLink = useQuery({ queryKey: ['mimi', 'attention-link', attentionLocator], queryFn: () => resolveMimiAttention(attentionLocator!), enabled: !!attentionLocator, retry: false, ...NO_POLLING_QUERY_OPTIONS })
  useEffect(() => { if (attentionLink.data) selectMimiConversation(attentionLink.data.conversation_id) }, [attentionLink.data])
  const currentTab = isMimiRoute ? 'mimi' : isTrackersRoute ? 'tracker' : activeScreen
  const mimiOpener = useRef<HTMLElement | null>(null)
  const mimiQuickAccess = useRef<HTMLButtonElement>(null)
  function openMimi() {
    if (currentTab === 'mimi') { focusMimiSurface(true); return }
    if (mimiDockOpen) { focusMimiSurface(); return }
    mimiOpener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    setMimiDockOpen(true)
  }
  function restoreMimiFocus() {
    const opener = mimiOpener.current
    const target = opener?.isConnected ? opener : mimiQuickAccess.current
    target?.focus({ preventScroll: true })
  }
  useEffect(() => {
    if (!session.mimi_available) return
    const shortcut = (event: KeyboardEvent) => {
      if (!acceptsMimiShortcut(event, document)) return
      event.preventDefault()
      openMimi()
    }
    window.addEventListener('keydown', shortcut)
    return () => window.removeEventListener('keydown', shortcut)
  })

  const [pinManageOpen,setPinManageOpen]=useState(false)
  const [pendingNavigation,setPendingNavigation]=useState<(()=>void)|null>(null)
  function leave(action:()=>void) {
    if(hasUnsavedFormChanges()||outboxState.admitting>0){setPendingNavigation(()=>action);return}
    action()
  }
  function selectTab(tab:AppScreen) {
    if(tab===currentTab&&location==='/')return
    leave(()=>{if(location!=='/')navigate('/');setActiveScreen(tab)})
  }
  function goToDefaultScreen(){selectTab('tasks')}

  const logout = useMutation({
    mutationFn: postLogout,
    // Full navigation, not cache surgery. Logging in is already a real page load
    // (the OAuth redirect), so logging out being one too keeps the two halves
    // symmetric - and it makes the server the single source of truth instead of
    // resting on how the query cache reacts to being invalidated or removed.
    onSuccess: () => { selectMimiConversation(null); window.location.assign('/') },
  })

  return (
    <div data-app-generation={import.meta.env.VITE_APP_GENERATION ?? 'v1'} className={cn('mimi-app-layout mx-auto grid w-full items-start gap-4',mimiDockOpen&&currentTab!=='mimi'?'mimi-app-with-dock max-w-[1920px]':currentTab==='mimi'?'max-w-[1920px]':currentTab==='calendar'&&location==='/'?'max-w-[1680px]':'max-w-[1440px]')} style={{'--mimi-dock-width':`${mimiDockWidth}px`} as import('react').CSSProperties}>
      <div className={cn('min-w-0 overflow-clip bg-background shadow-3 lg:rounded-xl',currentTab==='mimi'&&'mimi-app-workspace')}>
        <OfflineCoverage/><PwaUpdates/><DerivedPendingNotice/>
        {attentionLocator&&attentionLink.isError?<p role="alert" className="m-3 rounded-lg bg-warn-bg p-3 text-sm">Không mở được thông báo. Liên kết có thể không thuộc phiên này; chưa thực hiện thay đổi nào.</p>:null}
        {attentionLink.data?.expired?<p role="status" className="m-3 text-sm text-muted-foreground">Thông báo đã hết hạn; đang mở đúng hội thoại để đọc trạng thái hiện tại.</p>:null}
        <header data-testid="app-header" className={cn('sticky top-0 z-30 grid grid-cols-[auto_minmax(0,1fr)] items-center gap-2 border-b border-border/60 bg-background px-3 py-2 lg:grid-cols-[auto_minmax(0,1fr)_auto] lg:gap-4 lg:px-5',currentTab==='mimi'&&'mimi-app-header')}>
          <div className="min-w-max">
            <h1><Button asChild data-testid="app-logo-button" variant="ghost" size="lg" className="min-h-11 px-0 text-lg font-extrabold tracking-tight text-primary hover:bg-transparent hover:text-primary lg:text-xl" aria-label="Về trang Task mặc định"><a href="/" onClick={event=>{if(event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;event.preventDefault();goToDefaultScreen()}}>microSched</a></Button></h1>
            <p className="hidden text-xs capitalize text-muted-foreground lg:block">{todayLabel()}</p>
          </div>
          <DomainNavigation current={currentTab} mimiAvailable={session.mimi_available} onSelect={selectTab}/>
          <div data-testid="app-header-actions" className="flex min-w-0 max-w-full flex-wrap items-center justify-end gap-1">
            <ReminderCenter/>
            <OutboxPanel compact/>
            <PrivateGate session={session} compact manageOpen={pinManageOpen} onManageOpenChange={setPinManageOpen}/>
            <ApplicationMenu current={currentTab} mimiAvailable={session.mimi_available} onSelect={selectTab} onChat={openMimi} onPin={()=>setPinManageOpen(true)} onHome={()=>leave(()=>window.location.assign('/home'))} onSubscription={()=>leave(()=>navigate('/subscription'))} onLogout={()=>leave(()=>logout.mutate())} loggingOut={logout.isPending}/>
          </div>
        </header>
        <div className={cn('px-3 pb-[calc(5rem+env(safe-area-inset-bottom))] pt-4 sm:px-5 lg:pb-6',currentTab==='mimi'&&'pt-0')}>
          {currentTab!=='calendar'&&currentTab!=='mimi'&&!location.startsWith('/subscription')&&!location.startsWith('/reminder-confirm')?<div className="mb-2"><LiveStatus key={currentTab} tab={currentTab}/></div>:null}
          {location.startsWith('/subscription')?<SubscriptionScreen/>:location.startsWith('/reminder-confirm')?<ReminderConfirmScreen key={reminderDispatchKey}/>:<div id="app-domain-panel" role="tabpanel">
            {currentTab==='tasks'?<TasksScreen/>:null}
            {currentTab==='notes'?<NotesScreen/>:null}
            {currentTab==='calendar'?<CalendarScreen/>:null}
            {currentTab==='tracker'?<TrackerScreen privateUnlocked={outboxState.context.privateUntil>0}/>:null}
            {currentTab==='mimi'&&session.mimi_available?<MimiControlCenter onOpenDomain={domain=>selectTab(domain)} configurationOpen={mimiConfigurationOpen} onConfigurationOpenChange={setMimiConfigurationOpen}/>:null}
          </div>}
          {logout.isError?<p className="mt-4 text-sm text-bad">Không thể đăng xuất. Thử lại sau.</p>:null}
        </div>
      </div>
      {session.mimi_available?<MimiDock open={mimiDockOpen&&currentTab!=='mimi'} onOpenChange={setMimiDockOpen} onCloseFocus={restoreMimiFocus} onOpenTasks={()=>selectTab('tasks')} onOpenWorkspace={()=>{setMimiDockOpen(false);selectTab('mimi')}} onOpenConfiguration={()=>{setMimiDockOpen(false);selectTab('mimi');setMimiConfigurationOpen(true)}} width={mimiDockWidth} onWidthChange={setMimiDockWidth}/>:null}
      {session.mimi_available && !mimiDockOpen && currentTab !== 'mimi' ? <Tooltip><TooltipTrigger asChild>
        <Button ref={mimiQuickAccess} type="button" size="icon-lg" variant="outline" data-testid="mimi-quick-access" className="mimi-quick-access size-12 rounded-full bg-card shadow-3" aria-label="Chat với Mimi" aria-keyshortcuts="Alt+A" aria-controls="mimi-side-chat" aria-expanded={false} onClick={openMimi}><MimiAvatar size="md" /></Button>
      </TooltipTrigger><TooltipContent side="left">Chat với Mimi · Alt+A</TooltipContent></Tooltip> : null}
      <Dialog open={pendingNavigation!==null} onOpenChange={open=>{if(!open)setPendingNavigation(null)}}><DialogContent data-testid="leave-draft-confirm"><DialogHeader><DialogTitle>Rời nội dung chưa lưu?</DialogTitle><DialogDescription>Nội dung đang nhập chưa lưu sẽ mất. Bạn có thể ở lại để lưu trước. Các thay đổi đã lưu vào hàng đợi vẫn được giữ.</DialogDescription></DialogHeader>{outboxState.admitting>0?<p role="status">Đang lưu cục bộ. Đợi lưu xong trước khi rời.</p>:null}<div className="flex flex-wrap gap-2"><Button variant="outline" className="min-h-11" onClick={()=>setPendingNavigation(null)}>Ở lại</Button><Button variant="destructive" className="min-h-11" disabled={outboxState.admitting>0} onClick={()=>{const action=pendingNavigation;setPendingNavigation(null);action?.()}}>Rời bản nháp</Button></div></DialogContent></Dialog>
    </div>
  )
}

function App() {
  const outboxState = useOutbox()
  const location = useLocation()
  const session = useQuery({
    queryKey: ['session'],
    queryFn: fetchSession,
    networkMode: 'always',
    // The session has a long TTL. Window focus checks it when returning to the
    // tab; keeping no-poll explicit prevents future defaults from changing it.
    ...NO_POLLING_QUERY_OPTIONS,
    // Being logged out is an answer, not a failure worth retrying.
    retry: (failureCount, error) =>
      !(error instanceof UnauthenticatedError) && failureCount < 2,
  })

  const loggedOut = outboxState.authRequired || session.isError && session.error instanceof UnauthenticatedError
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
      <main className="min-h-screen bg-muted lg:px-6 lg:py-6">
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
          {session.data && !loggedOut && !session.isError ? <SignedIn session={session.data} /> : null}
        </div>
        <Toaster />
      </main>
    </TooltipProvider>
  )
}

export default App
