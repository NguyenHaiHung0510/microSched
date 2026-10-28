import { History, LoaderCircle, MoreVertical, Plus, SlidersHorizontal, SquareArrowOutUpRight, X, Wrench } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { DropdownMenu } from 'radix-ui'
import { MimiAvatar } from '@/components/brand'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { createMimiConversation, fetchCurrentMimiConversation } from '@/mimi-api'
import { MimiScreen } from '@/MimiScreen'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'
import { selectCreatedMimiConversation, useMimiSelection } from '@/mimi-selection'
import { useMimiConversationList } from '@/mimi-conversation-list'
import { mimiRunLabel } from '@/mimi-presentation'
import './mimi.css'
function useDesktopDock() {
  const [desktop, setDesktop] = useState(() => window.matchMedia('(min-width: 1280px)').matches)
  useEffect(() => { const media = window.matchMedia('(min-width: 1280px)'); const update = () => setDesktop(media.matches); media.addEventListener('change', update); return () => media.removeEventListener('change', update) }, [])
  return desktop
}
export function MimiDockButton({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return <Button type="button" data-testid="mimi-dock-toggle" size="lg" variant={open ? 'selected' : 'outline'} aria-expanded={open} aria-controls="mimi-side-chat" onClick={onToggle}><MimiAvatar size="sm" /><span className="hidden sm:inline">Chat với Mimi</span><span className="sm:hidden">Mimi</span></Button>
}
export function MimiDock({ open, onOpenChange, onOpenTasks, onOpenWorkspace, onOpenConfiguration, width, onWidthChange }: { open: boolean; onOpenChange: (open: boolean) => void; onOpenTasks: () => void; onOpenWorkspace: () => void; onOpenConfiguration: () => void; width: number; onWidthChange: (width: number) => void }) {
  const desktop = useDesktopDock()
  const client = useQueryClient()
  const [selectedId, setSelectedId] = useMimiSelection()
  const [historyOpen, setHistoryOpen] = useState(false)
  const [technicalOpen, setTechnicalOpen] = useState(false)
  const menuTrigger = useRef<HTMLButtonElement>(null)
  const drag = useRef<{ x: number; width: number } | null>(null)
  const current = useQuery({ queryKey: ['mimi', 'current'], queryFn: fetchCurrentMimiConversation, enabled: open, ...NO_POLLING_QUERY_OPTIONS })
  const conversations = useMimiConversationList('all')
  const id = selectedId ?? current.data?.id ?? conversations.items[0]?.id ?? null
  const create = useMutation({ mutationFn: createMimiConversation, onSuccess: (item) => { selectCreatedMimiConversation(client, item); void client.invalidateQueries({ queryKey: ['mimi'] }) } })
  const itemClass = 'flex min-h-11 cursor-pointer items-center gap-2 rounded-lg px-3 text-sm outline-none focus:bg-muted data-disabled:opacity-50'
  const menu = <DropdownMenu.Root><DropdownMenu.Trigger asChild><Button ref={menuTrigger} size="icon" variant="ghost" aria-label="Tùy chọn side-chat"><MoreVertical className="size-4" /></Button></DropdownMenu.Trigger><DropdownMenu.Portal><DropdownMenu.Content align="end" className="z-50 min-w-56 rounded-xl border bg-popover p-1 text-popover-foreground shadow-md"><DropdownMenu.Item className={itemClass} onSelect={onOpenWorkspace}><SquareArrowOutUpRight className="size-4" />Pop-out chat / Workspace</DropdownMenu.Item><DropdownMenu.Item className={itemClass} onSelect={() => setHistoryOpen(true)}><History className="size-4" />Lịch sử hội thoại</DropdownMenu.Item><DropdownMenu.Item className={itemClass} onSelect={() => { if (id) setSelectedId(id); onOpenConfiguration() }}><SlidersHorizontal className="size-4" />Cấu hình Mimi</DropdownMenu.Item><DropdownMenu.Separator className="my-1 border-t" /><DropdownMenu.Item className={itemClass} onSelect={() => setTechnicalOpen(true)}><Wrench className="size-4" />Chi tiết kỹ thuật</DropdownMenu.Item><DropdownMenu.Item disabled={create.isPending} className={itemClass} onSelect={() => create.mutate()}>{create.isPending ? <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" /> : <Plus className="size-4" />}Hội thoại mới</DropdownMenu.Item></DropdownMenu.Content></DropdownMenu.Portal></DropdownMenu.Root>
  const header = <div className="mimi-dock-header flex min-w-0 items-center justify-between gap-2 px-3 py-2"><div className="flex min-w-0 items-center gap-2"><MimiAvatar size="md" /><p className="truncate text-sm font-bold text-primary">Mimi</p></div><div className="flex shrink-0 items-center">{menu}<Button size="icon" variant="ghost" aria-label="Đóng side-chat" onClick={() => onOpenChange(false)}><X className="size-4" /></Button></div></div>
  const history = <Dialog open={historyOpen} onOpenChange={setHistoryOpen}><DialogContent className="max-h-[85dvh] overflow-auto"><DialogHeader><DialogTitle>Lịch sử hội thoại</DialogTitle><DialogDescription>Chọn tiêu đề để mở lại hội thoại đã lưu.</DialogDescription></DialogHeader>{conversations.isError ? <p role="alert">Chưa tải được lịch sử.</p> : null}<ul className="space-y-1">{conversations.items.map((item) => <li key={item.id}><Button variant="ghost" className="h-auto min-h-11 w-full justify-start whitespace-normal py-2 text-left" onClick={() => { setSelectedId(item.id); setHistoryOpen(false) }}><span className="min-w-0 flex-1"><span className="block truncate font-semibold">{item.title}</span><span className="block text-xs text-muted-foreground">{item.latest_run_state ? mimiRunLabel(item.latest_run_state) : 'Chưa có tin nhắn'} · {new Date(item.updated_at).toLocaleString('vi-VN')}</span></span>{item.id === id ? <span className="text-xs">Đang mở</span> : null}</Button></li>)}</ul>{conversations.hasNextPage ? <Button variant="outline" disabled={conversations.isFetchingNextPage} onClick={() => void conversations.fetchNextPage()}>Xem thêm hội thoại</Button> : null}</DialogContent></Dialog>
  const screen = <div className="min-h-0 min-w-0 flex-1 overflow-hidden p-2"><MimiScreen key={id} onOpenTasks={onOpenTasks} variant="dock" conversationId={id} onConversationCreated={setSelectedId} onOpenConfiguration={() => { if (id) setSelectedId(id); onOpenConfiguration() }} technicalOpen={technicalOpen} onTechnicalOpenChange={setTechnicalOpen} onTechnicalCloseFocus={() => menuTrigger.current?.focus()} /></div>
  if (!open) return null
  const resize = <div className="mimi-dock-resize" role="separator" aria-label="Đổi độ rộng side-chat" aria-orientation="vertical" aria-valuemin={320} aria-valuemax={600} aria-valuenow={width} tabIndex={0} onPointerDown={(event) => { event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); drag.current = { x: event.clientX, width } }} onPointerMove={(event) => { if (drag.current) onWidthChange(Math.max(320, Math.min(600, drag.current.width + drag.current.x - event.clientX))) }} onPointerUp={() => { drag.current = null }} onPointerCancel={() => { drag.current = null }} onLostPointerCapture={() => { drag.current = null }} onKeyDown={(event) => { const next = event.key === 'ArrowLeft' ? width + 16 : event.key === 'ArrowRight' ? width - 16 : event.key === 'Home' ? 320 : event.key === 'End' ? 600 : null; if (next !== null) { event.preventDefault(); onWidthChange(Math.max(320, Math.min(600, next))) } }} />
  if (desktop) return <aside id="mimi-side-chat" data-testid="mimi-side-chat" aria-label="Chat với Mimi" className="mimi-side-chat sticky top-4 flex h-[calc(100dvh-2rem)] min-h-0 min-w-0 flex-col rounded-xl">{resize}{header}{create.isError ? <p role="alert" className="p-2 text-xs text-bad">Chưa tạo được hội thoại: {create.error instanceof Error ? create.error.message : 'lỗi chưa rõ'}. Không tự gửi lại.</p> : null}{screen}{history}</aside>
  return <Dialog open onOpenChange={onOpenChange}><DialogContent id="mimi-side-chat" data-testid="mimi-side-chat" showCloseButton={false} className="mimi-side-chat inset-0 flex h-dvh max-h-dvh w-full min-w-0 max-w-full translate-x-0 translate-y-0 flex-col gap-0 overflow-hidden rounded-none p-0 sm:max-w-full"><DialogHeader className="sr-only"><DialogTitle>Chat với Mimi</DialogTitle><DialogDescription>Hội thoại STANDARD. Đóng side-chat không dừng run.</DialogDescription></DialogHeader>{header}{screen}{history}</DialogContent></Dialog>
}
