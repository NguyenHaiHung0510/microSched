import { LoaderCircle, PanelRightClose, PanelRightOpen, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { MimiAvatar } from '@/components/brand'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { createMimiConversation, fetchCurrentMimiConversation, fetchMimiConversations } from '@/mimi-api'
import { MimiScreen } from '@/MimiScreen'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'

function useDesktopDock(): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia('(min-width: 1280px)').matches)

  useEffect(() => {
    const query = window.matchMedia('(min-width: 1280px)')
    const update = () => setMatches(query.matches)
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])

  return matches
}

export function MimiDockButton({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <Button
      type="button"
      data-testid="mimi-dock-toggle"
      size="lg"
      variant={open ? 'selected' : 'outline'}
      aria-expanded={open}
      aria-controls="mimi-side-chat"
      onClick={onToggle}
    >
      {open ? <PanelRightClose aria-hidden="true" /> : <PanelRightOpen aria-hidden="true" />}
      <span className="hidden sm:inline">Chat với Mimi</span>
      <span className="sm:hidden">Mimi</span>
    </Button>
  )
}

export function MimiDock({
  open,
  onOpenChange,
  onOpenTasks,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onOpenTasks: () => void
}) {
  const desktop = useDesktopDock()
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const currentConv = useQuery({
    queryKey: ['mimi', 'current'],
    queryFn: fetchCurrentMimiConversation,
    ...NO_POLLING_QUERY_OPTIONS,
  })
  const conversations = useQuery({
    queryKey: ['mimi', 'conversations', 'active'],
    queryFn: () => fetchMimiConversations('active'),
    ...NO_POLLING_QUERY_OPTIONS,
  })

  const conversationItems = conversations.data?.items ?? []
  const effectiveSelectedId = selectedId && conversationItems.some((item) => item.id === selectedId)
    ? selectedId
    : currentConv.data?.id ?? conversationItems[0]?.id ?? null

  const create = useMutation({
    mutationFn: () => createMimiConversation(),
    onSuccess: (created) => {
      setSelectedId(created.id)
      void queryClient.invalidateQueries({ queryKey: ['mimi'] })
    },
  })

  if (!open) return null

  if (desktop) {
    return (
      <aside
        id="mimi-side-chat"
        data-testid="mimi-side-chat"
        aria-label="Chat với Mimi"
        className="sticky top-8 h-[calc(100vh-4rem)] min-w-0 overflow-hidden rounded-xl bg-background shadow-3"
      >
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between border-b px-3 py-2.5 gap-2">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <MimiAvatar size="sm" state="idle" />
              {conversationItems.length > 0 ? (
                <Select
                  value={effectiveSelectedId ?? ''}
                  onValueChange={(id) => setSelectedId(id)}
                >
                  <SelectTrigger
                    className="h-8 max-w-[14rem] text-xs font-semibold truncate border-none bg-muted/50 hover:bg-muted"
                    aria-label="Chọn cuộc trò chuyện"
                  >
                    <SelectValue placeholder="Chọn hội thoại…" />
                  </SelectTrigger>
                  <SelectContent>
                    {conversationItems.map((item) => (
                      <SelectItem key={item.id} value={item.id} className="text-xs truncate max-w-xs">
                        {item.title}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <div>
                  <p className="font-extrabold text-primary text-sm">Mimi</p>
                  <p className="text-xs text-muted-foreground">Side-chat</p>
                </div>
              )}
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <Button
                size="icon-sm"
                variant="ghost"
                title="Tạo cuộc trò chuyện mới"
                aria-label="Tạo cuộc trò chuyện mới"
                disabled={create.isPending}
                onClick={() => create.mutate()}
              >
                {create.isPending ? (
                  <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" />
                ) : (
                  <Plus className="size-4" />
                )}
              </Button>
              <Button size="icon-sm" variant="ghost" aria-label="Đóng side-chat" onClick={() => onOpenChange(false)}>
                <PanelRightClose className="size-4" aria-hidden="true" />
              </Button>
            </div>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              <MimiScreen onOpenTasks={onOpenTasks} variant="dock" conversationId={selectedId} onConversationCreated={setSelectedId} />
            </div>
          </div>
        </aside>
    )
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent
        id="mimi-side-chat"
        data-testid="mimi-side-chat"
        className="inset-0 h-dvh max-h-dvh w-full max-w-full translate-x-0 translate-y-0 content-start overflow-y-auto rounded-none p-4"
      >
        <DialogHeader>
          <div className="flex items-center justify-between w-full">
            <DialogTitle className="flex items-center gap-2"><MimiAvatar size="sm" state="idle" />Chat với Mimi</DialogTitle>
            <Button
              size="icon-sm"
              variant="ghost"
              title="Tạo cuộc trò chuyện mới"
              aria-label="Tạo cuộc trò chuyện mới"
              disabled={create.isPending}
              onClick={() => create.mutate()}
            >
              {create.isPending ? <LoaderCircle className="size-4 animate-spin" /> : <Plus className="size-4" />}
            </Button>
          </div>
          <DialogDescription>Conversation STANDARD hiện tại · nội dung chính vẫn giữ nguyên khi đóng.</DialogDescription>
        </DialogHeader>
        <MimiScreen onOpenTasks={onOpenTasks} variant="dock" conversationId={selectedId} onConversationCreated={setSelectedId} />
      </DialogContent>
    </Dialog>
  )
}
