import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, Archive, ArchiveRestore, BrainCircuit, CheckCircle2, CircleAlert, CircleDot, Clock3, Database, Gauge, History, LoaderCircle, MessagesSquare, MoreVertical, Orbit, PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, Pencil, Pin, PinOff, Play, Plus, ReceiptText, RotateCcw, Search, Settings2, ShieldCheck, Sparkles, TimerReset, WalletCards, Wrench } from 'lucide-react'
import { DropdownMenu } from 'radix-ui'
import { useEffect, useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { createMimiConversation, fetchCurrentMimiConversation, fetchMimiConversation, fetchMimiConversations, renameMimiConversation, setMimiConversationArchived, type MimiConversationSummary } from '@/mimi-api'
import { fetchMimiPreview, selectMimiPreviewScenario, type MimiPreviewRange, type MimiPreviewState, type MimiReasoningLevel } from '@/mimi-preview'
import { MimiAvatar } from '@/components/brand'
import { MimiContextRail } from '@/MimiContextRail'
import { MimiScreen } from '@/MimiScreen'
import { mimiRunLabel } from '@/mimi-presentation'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'

type CenterSection = 'overview' | 'activity' | 'conversations' | 'settings'

const sections: Array<{ id: CenterSection; label: string; icon: typeof Gauge }> = [
  { id: 'overview', label: 'Tổng quan', icon: Gauge },
  { id: 'activity', label: 'Hoạt động', icon: Activity },
  { id: 'conversations', label: 'Hội thoại', icon: MessagesSquare },
  { id: 'settings', label: 'Cấu hình', icon: Settings2 },
]

const rollingRanges: Array<{ id: MimiPreviewRange; label: string }> = [
  { id: 'today', label: 'Hôm nay' }, { id: '7d', label: '7 ngày' }, { id: '30d', label: '30 ngày' },
]
const calendarRanges: Array<{ id: MimiPreviewRange; label: string }> = [
  { id: 'week', label: 'Tuần này' }, { id: 'month', label: 'Tháng này' }, { id: 'quarter', label: 'Quý này' }, { id: 'year', label: 'Năm nay' },
]

const reasoningLevels: Array<{ id: MimiReasoningLevel; label: string; detail: string }> = [
  { id: 'minimal', label: 'Tối giản', detail: 'Trạng thái, elapsed time và tool đang chạy.' },
  { id: 'balanced', label: 'Cân bằng', detail: 'Thêm các mốc và suy luận công khai ngắn gọn.' },
  { id: 'detailed', label: 'Chi tiết', detail: 'Thêm toàn bộ reasoning summary và kết quả tool an toàn.' },
  { id: 'full', label: 'Đầy đủ', detail: 'Thêm timeline kỹ thuật, route, token và timing.' },
]

function formatMoney(value: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value)
}

function formatCompact(value: number) {
  return new Intl.NumberFormat('vi-VN', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

function useElapsed(acceptedAt?: string, running = false) {
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [running])
  if (!acceptedAt) return '—'
  const seconds = Math.max(0, Math.floor((nowMs - new Date(acceptedAt).getTime()) / 1000))
  return `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`
}

function StatCard({ title, value, description, icon: Icon }: { title: string; value: string; description: string; icon: typeof Gauge }) {
  return <Card className="gap-3"><CardHeader className="gap-2"><div className="flex items-center justify-between gap-3"><CardDescription>{title}</CardDescription><Icon className="size-5 text-primary" aria-hidden="true" /></div><CardTitle className="text-lg">{value}</CardTitle></CardHeader><CardContent><p className="text-sm text-muted-foreground">{description}</p></CardContent></Card>
}

function UsagePanel({ preview, range, onRange }: { preview: MimiPreviewState; range: MimiPreviewRange; onRange: (range: MimiPreviewRange) => void }) {
  const calendarMode = ['week', 'month', 'quarter', 'year'].includes(range)
  const visibleRanges = calendarMode ? calendarRanges : rollingRanges
  const maxCost = Math.max(...preview.usage.points.map((point) => point.cost), 0.01)
  return <Card className="min-w-0"><CardHeader><div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between"><div><div className="flex flex-wrap items-center gap-2"><CardTitle>Mức dùng AI</CardTitle><Badge variant="secondary">SYNTHETIC</Badge></div><CardDescription>{preview.usage.source}. Rolling neo vào hôm nay; kỳ lịch neo cứng theo tuần/tháng/quý/năm.</CardDescription></div><div className="space-y-2"><div className="grid grid-cols-2 gap-1" aria-label="Kiểu kỳ mức dùng"><Button size="sm" variant={!calendarMode ? 'selected' : 'ghost'} onClick={() => onRange('7d')}>Theo hôm nay</Button><Button size="sm" variant={calendarMode ? 'selected' : 'ghost'} onClick={() => onRange('week')}>Theo lịch</Button></div><div className="flex flex-wrap justify-end gap-1" aria-label="Khoảng thời gian mức dùng">{visibleRanges.map((item) => <Button key={item.id} size="sm" variant={range === item.id ? 'selected' : 'ghost'} onClick={() => onRange(item.id)}>{item.label}</Button>)}</div></div></div></CardHeader><CardContent className="space-y-4"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><div><p className="text-xs text-muted-foreground">Chi phí</p><p className="text-xl font-extrabold">{formatMoney(preview.usage.cost)}</p></div><div><p className="text-xs text-muted-foreground">Requests</p><p className="text-xl font-extrabold">{formatCompact(preview.usage.requests)}</p></div><div><p className="text-xs text-muted-foreground">Token</p><p className="text-xl font-extrabold">{formatCompact(preview.usage.total_tokens)}</p></div><div><p className="text-xs text-muted-foreground">Cache hit</p><p className="text-xl font-extrabold">{preview.usage.cache_hit_rate}%</p><p className="text-xs text-muted-foreground">{formatCompact(preview.usage.cached_tokens)} cached token</p></div></div><div className="flex h-36 items-end gap-2 rounded-xl bg-muted/50 p-3" role="img" aria-label="Chi phí theo các mốc trong khoảng đang chọn">{preview.usage.points.map((point) => <div key={point.label} className="flex min-w-0 flex-1 flex-col items-center justify-end gap-1"><span className="text-[11px] font-semibold">{formatMoney(point.cost)}</span><div className="w-full rounded-t bg-primary/80" style={{ height: `${Math.max(8, point.cost / maxCost * 82)}px` }} /><span className="max-w-full truncate text-[10px] text-muted-foreground">{point.label}</span></div>)}</div><details className="text-sm"><summary className="cursor-pointer font-semibold">Xem dữ liệu biểu đồ</summary><div className="mt-2 overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr><th className="py-2">Mốc</th><th>Chi phí</th><th>Requests</th><th>Cache</th></tr></thead><tbody>{preview.usage.points.map((point) => <tr key={point.label} className="border-t"><td className="py-2">{point.label}</td><td>{formatMoney(point.cost)}</td><td>{point.requests}</td><td>{point.cache_hit_rate}%</td></tr>)}</tbody></table></div></details></CardContent></Card>
}

function LiveRunPanel({ preview, reasoningLevel }: { preview: MimiPreviewState; reasoningLevel: MimiReasoningLevel }) {
  const running = preview.run.state === 'running' || preview.run.state === 'recovering'
  const elapsed = useElapsed(preview.run.accepted_at, running)
  const levelIndex = reasoningLevels.findIndex((item) => item.id === reasoningLevel)
  const stateLabel = preview.run.state === 'awaiting_owner' ? 'Chờ bạn' : preview.run.state === 'paused_deadline' ? 'Đã tạm dừng' : preview.run.state === 'recovering' ? 'Đang khôi phục' : preview.run.state === 'running' ? 'Đang chạy' : 'Đã xong'
  return <Card className={running ? 'border-primary/30' : undefined}><CardHeader><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2"><Sparkles className={running ? 'size-5 animate-pulse text-primary motion-reduce:animate-none' : 'size-5 text-primary'} aria-hidden="true" /><CardTitle>Run đang theo dõi</CardTitle></div><CardDescription>{preview.run.stage}</CardDescription></div><Badge variant={preview.run.state === 'recovering' ? 'destructive' : 'outline'}><CircleDot aria-hidden="true" />{stateLabel}</Badge></div></CardHeader><CardContent className="space-y-4"><div className="grid gap-3 sm:grid-cols-2"><div className="rounded-lg bg-muted/60 p-3"><p className="flex items-center gap-2 text-xs text-muted-foreground"><Clock3 className="size-4" />Thời gian từ khi nhận request</p><p className="mt-1 font-mono text-2xl font-extrabold">{elapsed}</p></div><div className="rounded-lg bg-muted/60 p-3"><p className="flex items-center gap-2 text-xs text-muted-foreground"><TimerReset className="size-4" />Giới hạn run hiện tại</p><p className="mt-1 font-bold">30 phút · có thể chỉnh</p><p className="text-xs text-muted-foreground">Chạm giới hạn sẽ tạm dừng rõ ràng và cho Resume.</p></div></div><p className="text-sm">{preview.run.summary}</p><ol className="space-y-2">{preview.run.tools.map((tool) => <li key={tool.label} className="flex items-center gap-3 rounded-lg border p-2.5 text-sm">{tool.state === 'done' ? <CheckCircle2 className="size-4 text-ok" /> : tool.state === 'running' ? <LoaderCircle className="size-4 animate-spin text-primary motion-reduce:animate-none" /> : <CircleDot className="size-4 text-muted-foreground" />}<span className="flex-1">{tool.label}</span><span className="text-xs text-muted-foreground">{tool.state === 'done' ? 'Xong' : tool.state === 'running' ? 'Đang làm' : 'Chờ'}</span></li>)}</ol>{levelIndex >= 1 && preview.run.reasoning.length ? <details open={reasoningLevel === 'detailed' || reasoningLevel === 'full'} className="rounded-lg bg-accent p-3 text-sm"><summary className="cursor-pointer font-semibold">Suy luận</summary><ul className="mt-2 space-y-1 text-accent-foreground">{preview.run.reasoning.slice(0, reasoningLevel === 'balanced' ? 1 : undefined).map((line) => <li key={line}>• {line}</li>)}</ul></details> : null}{levelIndex >= 3 ? <p className="rounded-lg border p-3 font-mono text-xs text-muted-foreground">run_id={preview.run.id} · route={preview.route.provider} · deadline={new Date(preview.run.deadline).toLocaleTimeString('vi-VN')}</p> : null}{preview.run.resumable ? <Button variant="outline"><Play />Resume sau khi reconcile</Button> : null}</CardContent></Card>
}

type WorkspaceDomain = 'tasks' | 'notes' | 'calendar' | 'tracker'

function ConversationWorkspace({ onOpenDomain }: { onOpenDomain: (domain: WorkspaceDomain) => void }) {
  const queryClient = useQueryClient()
  const [listState, setListState] = useState<'active' | 'archived'>('active')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [leftOpen, setLeftOpen] = useState(true)
  const [rightOpen, setRightOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [pinnedIds, setPinnedIds] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem('mimi_pinned_conversations')
      return saved ? JSON.parse(saved) : []
    } catch (err) {
      void err
      return []
    }
  })
  const [renameTarget, setRenameTarget] = useState<MimiConversationSummary | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const conversations = useQuery({ queryKey: ['mimi', 'conversations', listState], queryFn: () => fetchMimiConversations(listState), ...NO_POLLING_QUERY_OPTIONS })
  const conversationItems = useMemo(() => conversations.data?.items ?? [], [conversations.data?.items])
  const filteredItems = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return conversationItems
    return conversationItems.filter((item) => item.title.toLowerCase().includes(q))
  }, [conversationItems, searchQuery])
  const sortedItems = useMemo(() => {
    const pinned: MimiConversationSummary[] = []
    const unpinned: MimiConversationSummary[] = []
    for (const item of filteredItems) {
      if (pinnedIds.includes(item.id)) pinned.push(item)
      else unpinned.push(item)
    }
    return { pinned, unpinned }
  }, [filteredItems, pinnedIds])
  const effectiveSelectedId = selectedId && conversationItems.some((item) => item.id === selectedId) ? selectedId : conversationItems[0]?.id ?? null
  const selected = useQuery({ queryKey: ['mimi', 'conversation', effectiveSelectedId], queryFn: () => fetchMimiConversation(effectiveSelectedId!), enabled: Boolean(effectiveSelectedId), ...NO_POLLING_QUERY_OPTIONS })

  function togglePin(id: string) {
    setPinnedIds((prev) => {
      const next = prev.includes(id) ? prev.filter((item) => item !== id) : [id, ...prev]
      try {
        localStorage.setItem('mimi_pinned_conversations', JSON.stringify(next))
      } catch (err) {
        void err
      }
      return next
    })
  }
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ['mimi'] })
  const create = useMutation({ mutationFn: () => createMimiConversation(), onSuccess: (item) => { setListState('active'); setSelectedId(item.id); refresh() } })
  const rename = useMutation({ mutationFn: ({ item, title }: { item: MimiConversationSummary; title: string }) => renameMimiConversation(item, title), onSuccess: () => { setRenameTarget(null); refresh() } })
  const archive = useMutation({ mutationFn: ({ item, archived }: { item: MimiConversationSummary; archived: boolean }) => setMimiConversationArchived(item, archived), onSuccess: refresh })

  function renderConversationRow(item: MimiConversationSummary, isPinned: boolean) {
    const isRunning = item.latest_run_state === 'running' || item.latest_run_state === 'recovering'
    const isWaiting = item.latest_run_state === 'waiting_confirmation'
    const isUnreadCompleted = item.id !== effectiveSelectedId && item.latest_run_state === 'completed'
    const infoTooltip = [item.title, '• Chế độ: ' + (item.sensitivity ? item.sensitivity.toUpperCase() : 'STANDARD'), '• Trạng thái: ' + (item.latest_run_state ? mimiRunLabel(item.latest_run_state) : 'Sẵn sàng')].join('\n')

    return (
      <div
        key={item.id}
        className={'group relative flex items-center justify-between rounded-lg p-2 transition-colors ' + (effectiveSelectedId === item.id ? 'border border-primary/40 bg-primary/5 font-semibold text-primary' : 'hover:bg-muted/60 text-foreground')}
      >
        <button
          type="button"
          className="min-h-9 flex-1 min-w-0 text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          onClick={() => setSelectedId(item.id)}
          title={infoTooltip}
        >
          <div className="flex items-center gap-1.5 min-w-0">
            {isPinned ? <Pin className="size-3 text-primary fill-primary/30 shrink-0" aria-hidden="true" /> : null}
            <p className="line-clamp-1 text-xs truncate flex-1">{item.title}</p>
            {isRunning ? (
              <span title="Mimi đang xử lý ở nền" className="inline-flex shrink-0">
                <LoaderCircle className="size-3 animate-spin text-primary" aria-hidden="true" />
              </span>
            ) : null}
            {isWaiting ? (
              <span className="size-2 rounded-full bg-amber-500 shrink-0" title="Cần bạn xác nhận" aria-label="Cần bạn xác nhận" />
            ) : null}
            {isUnreadCompleted ? (
              <span className="size-1.5 rounded-full bg-primary/70 shrink-0" title="Đã có kết quả" />
            ) : null}
          </div>
          <div className="mt-0.5 flex items-center justify-between gap-1 text-[11px] font-normal text-muted-foreground">
            <span>{item.latest_run_state ? mimiRunLabel(item.latest_run_state) : 'Sẵn sàng'}</span>
            {item.archived_at ? <Archive className="size-3 text-muted-foreground" /> : null}
          </div>
        </button>
        <div className="shrink-0 ml-1">
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <Button
                size="icon-sm"
                variant="ghost"
                className="h-7 w-7 text-muted-foreground hover:text-foreground"
                aria-label={'Tùy chọn ' + item.title}
                title="Tùy chọn"
              >
                <MoreVertical className="size-3.5" />
              </Button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                align="end"
                className="z-50 min-w-[9.5rem] overflow-hidden rounded-xl border bg-popover p-1 text-popover-foreground shadow-md"
              >
                <DropdownMenu.Item
                  className="flex cursor-pointer select-none items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs outline-none hover:bg-muted focus:bg-muted"
                  onSelect={() => togglePin(item.id)}
                >
                  {isPinned ? <PinOff className="size-3.5 text-muted-foreground" /> : <Pin className="size-3.5 text-muted-foreground" />}
                  <span>{isPinned ? 'Bỏ ghim' : 'Ghim lên đầu'}</span>
                </DropdownMenu.Item>
                <DropdownMenu.Item
                  className="flex cursor-pointer select-none items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs outline-none hover:bg-muted focus:bg-muted"
                  onSelect={() => { setRenameTarget(item); setRenameDraft(item.title) }}
                >
                  <Pencil className="size-3.5 text-muted-foreground" />
                  <span>Đổi tên</span>
                </DropdownMenu.Item>
                <DropdownMenu.Separator className="my-1 h-px bg-muted" />
                <DropdownMenu.Item
                  className="flex cursor-pointer select-none items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs outline-none hover:bg-muted focus:bg-muted text-destructive"
                  onSelect={() => archive.mutate({ item, archived: !item.archived_at })}
                >
                  {item.archived_at ? <ArchiveRestore className="size-3.5" /> : <Archive className="size-3.5" />}
                  <span>{item.archived_at ? 'Khôi phục' : 'Lưu trữ'}</span>
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        </div>
      </div>
    )
  }

  const rail = <MimiContextRail conversation={selected.data} onOpenDomain={onOpenDomain} />
  return <div className="space-y-3">
    <div className="flex items-center justify-between gap-2 border-b pb-2">
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5 text-xs"
          onClick={() => setLeftOpen(!leftOpen)}
          title={leftOpen ? 'Thu gọn danh sách hội thoại' : 'Mở danh sách hội thoại'}
        >
          {leftOpen ? <PanelLeftClose className="size-4" /> : <PanelLeftOpen className="size-4" />}
          <span>{leftOpen ? 'Thu gọn hội thoại' : ('Hội thoại (' + conversationItems.length + ')')}</span>
        </Button>
        <span className="text-xs text-muted-foreground truncate max-w-[9rem] sm:max-w-sm font-medium">
          {selected.data?.title ? ('Đang mở: ' + selected.data.title) : 'Mimi Workspace'}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <Button
          variant={rightOpen ? 'selected' : 'outline'}
          size="sm"
          className="gap-1.5 text-xs"
          onClick={() => setRightOpen(!rightOpen)}
          title={rightOpen ? 'Đóng workspace rail' : 'Mở workspace rail (Task, Lịch, Notes)'}
        >
          {rightOpen ? <PanelRightClose className="size-4" /> : <PanelRightOpen className="size-4" />}
          <span>{rightOpen ? 'Đóng dữ liệu' : 'Xem dữ liệu liên quan'}</span>
        </Button>
      </div>
    </div>
    <div className="flex flex-col lg:flex-row min-w-0 items-start gap-4 w-full h-[calc(100dvh-5.5rem)] min-h-[40rem]">
      {leftOpen ? (
        <Card className="w-full lg:w-72 shrink-0 content-start shadow-xs h-full flex flex-col">
          <CardHeader className="p-3.5 pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-bold">Cuộc trò chuyện</CardTitle>
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label="Thu gọn danh sách"
                onClick={() => setLeftOpen(false)}
              >
                <PanelLeftClose className="size-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-2.5 p-3.5 pt-0 flex-1 min-h-0 flex flex-col">
            <Button className="w-full justify-start gap-2 rounded-xl text-xs font-semibold shadow-xs" disabled={create.isPending} onClick={() => create.mutate()}>
              {create.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none size-4" /> : <Plus className="size-4" />}
              Cuộc trò chuyện mới
            </Button>
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" aria-hidden="true" />
              <Input
                className="h-8 pl-8 text-xs rounded-lg bg-muted/40"
                placeholder="Tìm kiếm trong các cuộc trò chuyện…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-1 rounded-lg bg-muted/50 p-0.5">
              <Button size="sm" variant={listState === 'active' ? 'selected' : 'ghost'} className="h-7 text-xs" onClick={() => setListState('active')}>
                Đang dùng
              </Button>
              <Button size="sm" variant={listState === 'archived' ? 'selected' : 'ghost'} className="h-7 text-xs" onClick={() => setListState('archived')}>
                Đã lưu
              </Button>
            </div>
            {conversations.isPending ? <p role="status" className="py-4 text-center text-xs text-muted-foreground">Đang tải hội thoại…</p> : null}
            {conversations.isError ? <p role="alert" className="text-xs text-bad">Không tải được danh sách hội thoại.</p> : null}
            <div className="flex-1 min-h-0 space-y-2 overflow-y-auto pr-0.5">
              {sortedItems.pinned.length > 0 ? (
                <div className="space-y-1">
                  <p className="px-1 text-[11px] font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                    <Pin className="size-3" />Đã ghim
                  </p>
                  {sortedItems.pinned.map((item) => renderConversationRow(item, true))}
                </div>
              ) : null}
              {sortedItems.unpinned.length > 0 ? (
                <div className="space-y-1">
                  {sortedItems.pinned.length > 0 ? (
                    <p className="px-1 pt-1 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                      Gần đây
                    </p>
                  ) : null}
                  {sortedItems.unpinned.map((item) => renderConversationRow(item, false))}
                </div>
              ) : null}
            </div>
          </CardContent>
        </Card>
      ) : null}
      <div className="flex-1 min-w-0 flex justify-center h-full">
        <Card className="w-full max-w-4xl min-w-0 shadow-sm h-full flex flex-col">
          <CardContent className="p-4 sm:p-5 flex-1 min-h-0 flex flex-col">
            <MimiScreen
              onOpenTasks={() => onOpenDomain('tasks')}
              variant="workspace"
              conversationId={effectiveSelectedId}
              onConversationCreated={setSelectedId}
            />
          </CardContent>
        </Card>
      </div>
      {rightOpen ? <div className="w-full lg:w-80 shrink-0 h-full overflow-y-auto">{rail}</div> : null}
    </div>
    <Dialog open={Boolean(renameTarget)} onOpenChange={(open) => { if (!open) setRenameTarget(null) }}><DialogContent><DialogHeader><DialogTitle>Đổi tên hội thoại</DialogTitle><DialogDescription>Tên bạn đặt sẽ không bị auto-title ghi đè.</DialogDescription></DialogHeader><div className="space-y-2"><label htmlFor="mimi-conversation-title" className="text-sm font-semibold">Tên hội thoại</label><Input id="mimi-conversation-title" value={renameDraft} maxLength={80} onChange={(event) => setRenameDraft(event.target.value)} /><p className="text-right text-xs text-muted-foreground">{renameDraft.length}/80</p></div><DialogFooter><DialogClose asChild><Button variant="outline">Huỷ</Button></DialogClose><Button disabled={!renameDraft.trim() || rename.isPending || !renameTarget} onClick={() => { if (renameTarget) rename.mutate({ item: renameTarget, title: renameDraft }) }}>{rename.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : null}Lưu tên</Button></DialogFooter></DialogContent></Dialog>
  </div>
}

export function MimiControlCenter({ onOpenDomain }: { onOpenDomain: (domain: WorkspaceDomain) => void }) {
  const queryClient = useQueryClient()
  const [section, setSection] = useState<CenterSection>('overview')
  const [range, setRange] = useState<MimiPreviewRange>('7d')
  const [reasoningLevel, setReasoningLevel] = useState<MimiReasoningLevel>('balanced')
  const [leaseMinutes, setLeaseMinutes] = useState('30')
  const conversation = useQuery({ queryKey: ['mimi', 'current'], queryFn: fetchCurrentMimiConversation, ...NO_POLLING_QUERY_OPTIONS })
  const preview = useQuery({ queryKey: ['mimi', 'preview', range], queryFn: () => fetchMimiPreview(range), retry: false, staleTime: 0 })
  const selectScenario = useMutation({ mutationFn: selectMimiPreviewScenario, onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['mimi', 'preview'] }); void queryClient.invalidateQueries({ queryKey: ['mimi', 'current'] }) } })
  const current = conversation.data
  const synthetic = preview.data
  const latestRun = current?.runs.at(-1)
  const pendingApprovals = synthetic?.attention.pending_approvals ?? current?.change_sets.filter((item) => item.state === 'pending').length ?? 0
  const unresolvedFeedback = synthetic?.attention.unresolved_feedback ?? current?.feedback.filter((item) => item.unresolved).length ?? 0
  const scenarioDescription = useMemo(() => synthetic?.scenarios.find((item) => item.id === synthetic.scenario)?.description, [synthetic])

  return <section className="space-y-5" aria-labelledby="mimi-control-title">
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div className="space-y-1"><div className="flex items-center gap-2"><MimiAvatar size="sm" state="idle" /><h2 id="mimi-control-title" className="text-2xl font-extrabold text-primary">Mimi Control Center</h2></div><p className="max-w-2xl text-sm text-muted-foreground">Quản lý trạng thái, mức dùng, hoạt động, hội thoại và cấu hình đang thực sự có hiệu lực.</p></div><div className="flex flex-wrap items-center gap-2"><Badge variant="outline">P1R · local preview</Badge>{synthetic ? <Badge variant="secondary">Synthetic data</Badge> : null}</div></div>
    {synthetic ? <Card className="border-dashed bg-muted/30"><CardContent className="flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-sm font-bold">Kịch bản để duyệt UX</p><p className="text-xs text-muted-foreground">{scenarioDescription}</p></div><Select value={synthetic.scenario} onValueChange={(value) => selectScenario.mutate(value)} disabled={selectScenario.isPending}><SelectTrigger className="min-h-11 w-full bg-card sm:w-56" aria-label="Kịch bản synthetic"><SelectValue /></SelectTrigger><SelectContent>{synthetic.scenarios.map((scenario) => <SelectItem key={scenario.id} value={scenario.id}>{scenario.label}</SelectItem>)}</SelectContent></Select></CardContent></Card> : null}
    <nav className="flex gap-2 overflow-x-auto pb-1" aria-label="Khu quản lý Mimi">{sections.map(({ id, label, icon: Icon }) => <Button key={id} size="lg" variant={section === id ? 'selected' : 'ghost'} aria-current={section === id ? 'page' : undefined} onClick={() => setSection(id)}><Icon aria-hidden="true" />{label}</Button>)}</nav>

    {section === 'overview' ? <div className="space-y-5"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><StatCard title="Trạng thái Mimi" value={conversation.isError ? 'Cần kết nối lại' : synthetic?.run.state === 'running' ? 'Đang làm việc' : 'Sẵn sàng'} description="Browser focus không quyết định vòng đời run." icon={conversation.isError ? CircleAlert : CheckCircle2} /><StatCard title="Route hiệu lực" value={synthetic ? synthetic.route.model : 'Chưa đủ route-card'} description={synthetic ? `${synthetic.route.provider} · ${synthetic.route.mode}` : 'Backend thật sẽ công bố model/provider.'} icon={BrainCircuit} /><StatCard title="Chờ bạn" value={`${pendingApprovals} preview`} description={`${unresolvedFeedback} feedback còn mở · mọi ghi Task vẫn cần xác nhận.`} icon={ShieldCheck} /><StatCard title="Run gần nhất" value={synthetic ? synthetic.run.stage : latestRun ? mimiRunLabel(latestRun.state) : 'Chưa có'} description="Elapsed, route, tool và terminal state nằm ở Activity." icon={Activity} /></div>{synthetic ? <UsagePanel preview={synthetic} range={range} onRange={setRange} /> : null}<div className="grid gap-4 lg:grid-cols-[minmax(0,1.25fr)_minmax(18rem,0.75fr)]">{synthetic ? <LiveRunPanel preview={synthetic} reasoningLevel={reasoningLevel} /> : null}<Card><CardHeader><CardTitle>Health & capability</CardTitle><CardDescription>Trạng thái tách bạch, không gộp “Online” thành một nhãn mơ hồ.</CardDescription></CardHeader><CardContent className="space-y-3">{synthetic?.health.map((item) => <div key={item.label} className="flex items-start gap-3 rounded-lg bg-muted/50 p-3"><span className={`mt-1 size-2.5 rounded-full ${item.state === 'good' ? 'bg-ok' : item.state === 'idle' ? 'bg-muted-foreground' : item.state === 'warning' ? 'bg-warn' : 'bg-bad'}`} /><div><p className="text-sm font-semibold">{item.label}</p><p className="text-xs text-muted-foreground">{item.detail}</p></div></div>) ?? <p className="text-sm text-muted-foreground">Chờ backend công bố health có provenance.</p>}<div className="border-t pt-3 text-sm"><p className="flex items-center gap-2 font-semibold"><Orbit className="size-4" />Orbit chưa bật</p><p className="mt-1 text-xs text-muted-foreground">Chỉ xuất hiện thành module khi có jobs/report thật.</p></div></CardContent></Card></div></div> : null}

    {section === 'activity' ? <div className="space-y-4">{synthetic ? <LiveRunPanel preview={synthetic} reasoningLevel={reasoningLevel} /> : null}<Card><CardHeader><CardTitle>Runs, receipts và diagnostics</CardTitle><CardDescription>Run không chết khi đóng side-chat, đổi tab, đổi hội thoại hoặc đóng browser; server lease mới là ranh giới.</CardDescription></CardHeader><CardContent><div className="grid gap-3 sm:grid-cols-3"><div className="rounded-lg bg-muted/50 p-3"><ReceiptText className="mb-2 size-5 text-primary" /><p className="font-bold">Receipt bền vững</p><p className="text-xs text-muted-foreground">Gắn đúng operation, không trộn transcript.</p></div><div className="rounded-lg bg-muted/50 p-3"><History className="mb-2 size-5 text-primary" /><p className="font-bold">Replay theo sequence</p><p className="text-xs text-muted-foreground">Reconnect cùng run ID, không dispatch lần hai.</p></div><div className="rounded-lg bg-muted/50 p-3"><Database className="mb-2 size-5 text-primary" /><p className="font-bold">Checkpoint có ý nghĩa</p><p className="text-xs text-muted-foreground">Không poll DB để giữ Neon luôn bật.</p></div></div></CardContent></Card></div> : null}

    {section === 'conversations' ? <ConversationWorkspace onOpenDomain={onOpenDomain} /> : null}

    {section === 'settings' ? <div className="grid gap-4 lg:grid-cols-2"><Card><CardHeader><div className="flex items-center gap-2"><TimerReset className="size-5 text-primary" /><CardTitle>Runtime & hiển thị</CardTitle></div><CardDescription>Một cụm cấu hình, một nút về mặc định.</CardDescription></CardHeader><CardContent className="space-y-5"><div className="space-y-2"><label className="text-sm font-semibold" htmlFor="mimi-lease">Giới hạn mỗi run</label><Select value={leaseMinutes} onValueChange={setLeaseMinutes}><SelectTrigger id="mimi-lease" className="min-h-11 w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="15">15 phút</SelectItem><SelectItem value="30">30 phút · mặc định</SelectItem><SelectItem value="60">60 phút</SelectItem><SelectItem value="120">120 phút</SelectItem></SelectContent></Select><p className="text-xs text-muted-foreground">Hết thời gian: tạm dừng rõ ràng, checkpoint và cho Resume; không tự retry outcome chưa biết.</p></div><div className="space-y-2"><label className="text-sm font-semibold" htmlFor="mimi-reasoning">Mức hiển thị hoạt động</label><Select value={reasoningLevel} onValueChange={(value) => setReasoningLevel(value as MimiReasoningLevel)}><SelectTrigger id="mimi-reasoning" className="min-h-11 w-full"><SelectValue /></SelectTrigger><SelectContent>{reasoningLevels.map((level) => <SelectItem key={level.id} value={level.id}>{level.label}</SelectItem>)}</SelectContent></Select><ol className="space-y-1 text-xs text-muted-foreground">{reasoningLevels.slice(0, reasoningLevels.findIndex((item) => item.id === reasoningLevel) + 1).map((level) => <li key={level.id}><b className="text-foreground">{level.label}:</b> {level.detail}</li>)}</ol></div><Dialog><DialogTrigger asChild><Button variant="outline"><RotateCcw />Về mặc định</Button></DialogTrigger><DialogContent><DialogHeader><DialogTitle>Đưa Runtime & hiển thị về mặc định?</DialogTitle><DialogDescription>Giới hạn run sẽ là 30 phút và mức hiển thị sẽ là Cân bằng. Run đang chạy không bị thay đổi.</DialogDescription></DialogHeader><DialogFooter><DialogClose asChild><Button variant="outline">Giữ nguyên</Button></DialogClose><DialogClose asChild><Button onClick={() => { setLeaseMinutes('30'); setReasoningLevel('balanced') }}>Về mặc định</Button></DialogClose></DialogFooter></DialogContent></Dialog></CardContent></Card><Card><CardHeader><div className="flex items-center gap-2"><WalletCards className="size-5 text-primary" /><CardTitle>Nguồn dữ liệu & credential</CardTitle></div><CardDescription>Chỉ hiện cấu hình có thật; secret không bao giờ xuống browser.</CardDescription></CardHeader><CardContent className="space-y-3 text-sm"><div className="flex items-start gap-3 rounded-lg bg-muted/50 p-3"><ShieldCheck className="mt-0.5 size-5 text-primary" /><div><p className="font-semibold">OpenRouter management key</p><p className="text-xs text-muted-foreground">Server-only, quyền tối thiểu cho analytics. Sẽ xin bạn cung cấp khi bắt đầu tích hợp live.</p></div></div><div className="flex items-start gap-3 rounded-lg bg-muted/50 p-3"><Gauge className="mt-0.5 size-5 text-primary" /><div><p className="font-semibold">Kỳ dữ liệu theo capability</p><p className="text-xs text-muted-foreground">Rolling hôm nay/7/30 ngày và kỳ lịch tuần/tháng/quý/năm chỉ hiện khi nguồn có dữ liệu; snapshot giữ lịch sử nguồn ngắn.</p></div></div><div className="flex items-start gap-3 rounded-lg bg-muted/50 p-3"><Wrench className="mt-0.5 size-5 text-primary" /><div><p className="font-semibold">Reasoning là capability phụ</p><p className="text-xs text-muted-foreground">Không có vẫn route và MIDEX bình thường; UI rơi về stage/tool events.</p></div></div></CardContent></Card></div> : null}
  </section>
}
