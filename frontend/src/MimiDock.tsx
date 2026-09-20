import { PanelRightClose, PanelRightOpen } from 'lucide-react'
import { useEffect, useState } from 'react'

import { MimiAvatar } from '@/components/brand'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { MimiScreen } from '@/MimiScreen'

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
          <div className="flex items-center justify-between border-b px-4 py-3">
            <div className="flex items-center gap-2">
              <MimiAvatar size="sm" state="idle" />
              <div>
                <p className="font-extrabold text-primary">Mimi</p>
                <p className="text-xs text-muted-foreground">Side-chat · conversation hiện tại</p>
              </div>
            </div>
            <Button size="icon-lg" variant="ghost" aria-label="Đóng side-chat" onClick={() => onOpenChange(false)}>
              <PanelRightClose aria-hidden="true" />
            </Button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            <MimiScreen onOpenTasks={onOpenTasks} variant="dock" />
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
          <DialogTitle className="flex items-center gap-2"><MimiAvatar size="sm" state="idle" />Chat với Mimi</DialogTitle>
          <DialogDescription>Conversation STANDARD hiện tại · nội dung chính vẫn giữ nguyên khi đóng.</DialogDescription>
        </DialogHeader>
        <MimiScreen onOpenTasks={onOpenTasks} variant="dock" />
      </DialogContent>
    </Dialog>
  )
}
