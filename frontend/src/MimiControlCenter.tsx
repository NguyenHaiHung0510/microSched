import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, ArchiveRestore, LoaderCircle, MoreVertical, PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, Pencil, Pin, PinOff, Plus, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { DropdownMenu } from 'radix-ui'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { createMimiConversation, fetchMimiConversation, renameMimiConversation, setMimiConversationArchived, type MimiConversationSummary } from '@/mimi-api'
import { useMimiConversationList } from '@/mimi-conversation-list'
import { selectCreatedMimiConversation, useMimiSelection } from '@/mimi-selection'
import { mimiRunLabel } from '@/mimi-presentation'
import { MimiContextRail } from '@/MimiContextRail'
import { MimiScreen } from '@/MimiScreen'
import { MimiNotifications } from '@/MimiNotifications'
import { MimiRailResize } from '@/MimiRailResize'
import { rememberedMimiWidth, rememberMimiWidth, useWideMimi } from '@/mimi-layout'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'
import './mimi.css'
type WorkspaceDomain = 'tasks' | 'notes' | 'calendar' | 'tracker'
function ConversationWorkspace({ onOpenDomain }: { onOpenDomain: (domain: WorkspaceDomain) => void }) {
  const queryClient = useQueryClient()
  const [listState, setListState] = useState<'active' | 'archived'>('active')
  const [selectedId, setSelectedId] = useMimiSelection()
  const [leftOpen, setLeftOpen] = useState(true)
  const [rightOpen, setRightOpen] = useState(true)
  const wide = useWideMimi()
  const [mobileRail, setMobileRail] = useState<'left' | 'right' | null>(null)
  const [leftWidth, setLeftWidth] = useState(() => rememberedMimiWidth('left', 200))
  const [rightWidth, setRightWidth] = useState(() => rememberedMimiWidth('right', 220))
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
  const conversations = useMimiConversationList(listState)
  const conversationItems = conversations.items
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
  const effectiveSelectedId = selectedId ?? conversationItems[0]?.id ?? null
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
  const create = useMutation({ mutationFn: () => createMimiConversation(), onSuccess: (item) => { setListState('active'); selectCreatedMimiConversation(queryClient, item); refresh() } })
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
        <Button
          variant="ghost"
          type="button"
          className="min-h-11 h-auto block flex-1 min-w-0 px-0 text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          onClick={() => setSelectedId(item.id)}
          title={infoTooltip}
        >
          <div className="flex items-center gap-1.5 min-w-0">
            {isPinned ? <Pin className="size-3 text-primary fill-primary/30 shrink-0" aria-hidden="true" /> : null}
            <p className="line-clamp-1 text-xs truncate flex-1">{item.title}</p>
            {isRunning ? (
              <span title="Mimi đang xử lý ở nền" className="inline-flex shrink-0">
                <LoaderCircle className="size-3 animate-spin motion-reduce:animate-none text-primary" aria-hidden="true" />
              </span>
            ) : null}
            {isWaiting ? (
              <span className="size-2 rounded-full bg-warn shrink-0" title="Cần bạn xác nhận" aria-label="Cần bạn xác nhận" />
            ) : null}
            {isUnreadCompleted ? (
              <span className="size-1.5 rounded-full bg-primary/70 shrink-0" title="Đã có kết quả" />
            ) : null}
          </div>
          <div className="mt-0.5 flex items-center justify-between gap-1 text-xs font-normal text-muted-foreground">
            <span className="min-w-0 truncate">{item.id === effectiveSelectedId && selected.data?.messages.at(-1)?.content ? selected.data.messages.at(-1)!.content.slice(0, 100) : item.latest_run_state ? mimiRunLabel(item.latest_run_state) : 'Chưa có tin nhắn'}</span>
            {item.archived_at ? <Archive className="size-3 text-muted-foreground" /> : null}
          </div>
        </Button>
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

  const rail = <><MimiNotifications conversationId={effectiveSelectedId} /><MimiContextRail conversation={selected.data} onOpenDomain={onOpenDomain} /></>
  return <div className="mimi-workspace-shell">
    <div className="mimi-workspace-toolbar flex flex-wrap items-center justify-between gap-2">
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          className="min-h-11 min-w-11 shrink-0 gap-1.5 text-xs"
          onClick={() => wide ? setLeftOpen(!leftOpen) : setMobileRail(mobileRail === 'left' ? null : 'left')}
          title={leftOpen ? 'Thu gọn danh sách hội thoại' : 'Mở danh sách hội thoại'}
        >
          {leftOpen ? <PanelLeftClose className="size-4" /> : <PanelLeftOpen className="size-4" />}
          <span className="hidden sm:inline">{leftOpen ? 'Thu gọn hội thoại' : ('Hội thoại (' + conversationItems.length + ')')}</span><span className="sr-only sm:hidden">Hội thoại</span>
        </Button>
        <span className="min-w-0 flex-1 text-xs text-muted-foreground truncate max-w-[9rem] sm:max-w-sm font-medium">
          {selected.data?.title ? ('Đang mở: ' + selected.data.title) : 'Mimi Workspace'}
        </span>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Button
          variant={rightOpen ? 'selected' : 'outline'}
          size="sm"
          className="min-h-11 min-w-11 gap-1.5 text-xs"
          onClick={() => wide ? setRightOpen(!rightOpen) : setMobileRail(mobileRail === 'right' ? null : 'right')}
          title={rightOpen ? 'Đóng workspace rail' : 'Mở workspace rail (Task, Lịch, Notes)'}
        >
          {rightOpen ? <PanelRightClose className="size-4" /> : <PanelRightOpen className="size-4" />}
          <span className="hidden sm:inline">{rightOpen ? 'Đóng dữ liệu' : 'Xem dữ liệu liên quan'}</span><span className="sr-only sm:hidden">Dữ liệu và thông báo</span>
        </Button>
      </div>
    </div>
    <div className="mimi-workspace" data-testid="mimi-workspace" style={{ '--mimi-left': `${leftOpen ? leftWidth : 44}px`, '--mimi-right': `${rightOpen ? rightWidth : 44}px` } as import('react').CSSProperties}>
      <aside className="mimi-workspace-rail" aria-label="Rail hội thoại" data-testid="mimi-left-rail">{leftOpen ?         <Card className="mimi-left-rail min-w-0 h-full flex flex-col overflow-hidden border-0 rounded-none shadow-none">
          <CardHeader className="p-3.5 pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-bold">Cuộc trò chuyện</CardTitle>
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label="Thu gọn danh sách"
                onClick={() => wide ? setLeftOpen(false) : setMobileRail(null)}
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
                aria-label="Tìm cuộc trò chuyện" className="min-h-11 pl-8 text-base md:text-sm rounded-lg bg-muted/40"
                placeholder="Tìm kiếm trong các cuộc trò chuyện…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-1 rounded-lg bg-muted/50 p-0.5">
              <Button size="sm" variant={listState === 'active' ? 'selected' : 'ghost'} className="min-h-11 text-xs" onClick={() => setListState('active')}>
                Đang dùng
              </Button>
              <Button size="sm" variant={listState === 'archived' ? 'selected' : 'ghost'} className="min-h-11 text-xs" onClick={() => setListState('archived')}>
                Đã lưu
              </Button>
            </div>
            {create.isError ? <p role="alert" className="text-xs text-bad">Chưa tạo được hội thoại: {create.error instanceof Error ? create.error.message : 'lỗi chưa rõ'}. Không tự gửi lại.</p> : null}
            {rename.isError || archive.isError ? <p role="alert" className="text-xs text-bad">Chưa lưu được thay đổi hội thoại; đọc lại trạng thái trước khi thao tác tiếp.</p> : null}
            {conversations.isPending ? <p role="status" className="py-4 text-center text-xs text-muted-foreground">Đang tải hội thoại…</p> : null}
            {conversations.isError ? <p role="alert" className="text-xs text-bad">Không tải được danh sách hội thoại.</p> : null}
            <div className="flex-1 min-h-0 space-y-2 overflow-y-auto overflow-x-hidden pr-0.5">
              {sortedItems.pinned.length > 0 ? (
                <div className="space-y-1">
                  <p className="px-1 text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                    <Pin className="size-3" />Đã ghim
                  </p>
                  {sortedItems.pinned.map((item) => renderConversationRow(item, true))}
                </div>
              ) : null}
              {sortedItems.unpinned.length > 0 ? (
                <div className="space-y-1">
                  {sortedItems.pinned.length > 0 ? (
                    <p className="px-1 pt-1 text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      Gần đây
                    </p>
                  ) : null}
                  {sortedItems.unpinned.map((item) => renderConversationRow(item, false))}
                </div>
              ) : null}
              {conversations.hasNextPage ? <Button className="w-full" variant="outline" disabled={conversations.isFetchingNextPage} onClick={() => void conversations.fetchNextPage()}>{conversations.isFetchingNextPage ? 'Đang tải…' : 'Xem thêm hội thoại'}</Button> : null}
              {searchQuery && conversations.hasNextPage ? <p className="text-xs text-muted-foreground">Tìm trong lịch sử đã tải. Xem thêm để tìm hội thoại cũ hơn.</p> : null}
            </div>
          </CardContent>
        </Card> : <Button size="icon" variant="ghost" aria-label="Mở rail hội thoại" onClick={() => setLeftOpen(true)}><PanelLeftOpen /></Button>}</aside>
      <MimiRailResize side="left" width={leftWidth} onResize={(width) => { setLeftWidth(width); rememberMimiWidth('left', width) }} disabled={!leftOpen} />
      <main className="mimi-center min-h-0 min-w-0 overflow-hidden rounded-xl p-3" data-testid="mimi-workspace-center">
        <MimiScreen key={effectiveSelectedId} onOpenTasks={() => onOpenDomain('tasks')} conversationId={effectiveSelectedId} onConversationCreated={setSelectedId} />
      </main>
      <MimiRailResize side="right" width={rightWidth} onResize={(width) => { setRightWidth(width); rememberMimiWidth('right', width) }} disabled={!rightOpen} />
      <aside className="mimi-workspace-rail mimi-right-rail" aria-label="Rail dữ liệu" data-testid="mimi-right-rail">{rightOpen ? rail : <Button size="icon" variant="ghost" aria-label="Mở rail dữ liệu" onClick={() => setRightOpen(true)}><PanelRightOpen /></Button>}</aside>
    </div>
    <Dialog open={!wide && mobileRail !== null} onOpenChange={(open) => { if (!open) setMobileRail(null) }}><DialogContent className="max-h-[85dvh] overflow-y-auto"><DialogHeader><DialogTitle>{mobileRail === 'left' ? 'Hội thoại' : 'Dữ liệu và thông báo'}</DialogTitle><DialogDescription>Mở riêng rail để giữ chỗ cho cuộc trò chuyện trên màn hình nhỏ.</DialogDescription></DialogHeader>{mobileRail === 'left' ?         <Card className="mimi-left-rail min-w-0 h-full flex flex-col overflow-hidden border-0 rounded-none shadow-none">
          <CardHeader className="p-3.5 pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-bold">Cuộc trò chuyện</CardTitle>
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label="Thu gọn danh sách"
                onClick={() => wide ? setLeftOpen(false) : setMobileRail(null)}
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
                aria-label="Tìm cuộc trò chuyện" className="min-h-11 pl-8 text-base md:text-sm rounded-lg bg-muted/40"
                placeholder="Tìm kiếm trong các cuộc trò chuyện…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-1 rounded-lg bg-muted/50 p-0.5">
              <Button size="sm" variant={listState === 'active' ? 'selected' : 'ghost'} className="min-h-11 text-xs" onClick={() => setListState('active')}>
                Đang dùng
              </Button>
              <Button size="sm" variant={listState === 'archived' ? 'selected' : 'ghost'} className="min-h-11 text-xs" onClick={() => setListState('archived')}>
                Đã lưu
              </Button>
            </div>
            {create.isError ? <p role="alert" className="text-xs text-bad">Chưa tạo được hội thoại: {create.error instanceof Error ? create.error.message : 'lỗi chưa rõ'}. Không tự gửi lại.</p> : null}
            {rename.isError || archive.isError ? <p role="alert" className="text-xs text-bad">Chưa lưu được thay đổi hội thoại; đọc lại trạng thái trước khi thao tác tiếp.</p> : null}
            {conversations.isPending ? <p role="status" className="py-4 text-center text-xs text-muted-foreground">Đang tải hội thoại…</p> : null}
            {conversations.isError ? <p role="alert" className="text-xs text-bad">Không tải được danh sách hội thoại.</p> : null}
            <div className="flex-1 min-h-0 space-y-2 overflow-y-auto overflow-x-hidden pr-0.5">
              {sortedItems.pinned.length > 0 ? (
                <div className="space-y-1">
                  <p className="px-1 text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                    <Pin className="size-3" />Đã ghim
                  </p>
                  {sortedItems.pinned.map((item) => renderConversationRow(item, true))}
                </div>
              ) : null}
              {sortedItems.unpinned.length > 0 ? (
                <div className="space-y-1">
                  {sortedItems.pinned.length > 0 ? (
                    <p className="px-1 pt-1 text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      Gần đây
                    </p>
                  ) : null}
                  {sortedItems.unpinned.map((item) => renderConversationRow(item, false))}
                </div>
              ) : null}
              {conversations.hasNextPage ? <Button className="w-full" variant="outline" disabled={conversations.isFetchingNextPage} onClick={() => void conversations.fetchNextPage()}>{conversations.isFetchingNextPage ? 'Đang tải…' : 'Xem thêm hội thoại'}</Button> : null}
              {searchQuery && conversations.hasNextPage ? <p className="text-xs text-muted-foreground">Tìm trong lịch sử đã tải. Xem thêm để tìm hội thoại cũ hơn.</p> : null}
            </div>
          </CardContent>
        </Card> : rail}</DialogContent></Dialog>

    <Dialog open={Boolean(renameTarget)} onOpenChange={(open) => { if (!open) setRenameTarget(null) }}><DialogContent><DialogHeader><DialogTitle>Đổi tên hội thoại</DialogTitle><DialogDescription>Tên bạn đặt sẽ không bị auto-title ghi đè.</DialogDescription></DialogHeader><div className="space-y-2"><label htmlFor="mimi-conversation-title" className="text-sm font-semibold">Tên hội thoại</label><Input id="mimi-conversation-title" value={renameDraft} maxLength={80} onChange={(event) => setRenameDraft(event.target.value)} /><p className="text-right text-xs text-muted-foreground">{renameDraft.length}/80</p></div><DialogFooter><DialogClose asChild><Button variant="outline">Huỷ</Button></DialogClose><Button disabled={!renameDraft.trim() || rename.isPending || !renameTarget} onClick={() => { if (renameTarget) rename.mutate({ item: renameTarget, title: renameDraft }) }}>{rename.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : null}Lưu tên</Button></DialogFooter></DialogContent></Dialog>
  </div>
}

export function MimiControlCenter({ onOpenDomain }: { onOpenDomain: (domain: WorkspaceDomain) => void }) { return <ConversationWorkspace onOpenDomain={onOpenDomain} /> }
