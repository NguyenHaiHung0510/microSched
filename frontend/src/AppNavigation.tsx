import { useRef, useState, useSyncExternalStore } from 'react'
import { BookOpen, ChevronRight, CreditCard, Grid2X2, KeyRound, LogOut, MessagesSquare } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { APP_SCREENS, quickScreens, type AppScreen } from '@/app-navigation'

const desktopMedia = '(min-width: 1024px)'
function subscribeDesktop(notify: () => void) {
  const media = window.matchMedia(desktopMedia)
  media.addEventListener('change', notify)
  return () => media.removeEventListener('change', notify)
}

export function DomainNavigation({current,mimiAvailable,gardenAvailable,onSelect}:{current:AppScreen|null;mimiAvailable:boolean;gardenAvailable:boolean;onSelect:(screen:AppScreen)=>void}) {
  const desktop = useSyncExternalStore(subscribeDesktop, () => window.matchMedia(desktopMedia).matches, () => false)
  const screens = quickScreens(gardenAvailable, desktop)
  const focusable = screens.filter(({id}) => id !== 'mimi' || mimiAvailable)
  const focusTab = focusable.some(({id}) => id === current) ? current : focusable[0]?.id
  return <nav aria-label="Nội dung ứng dụng" className="app-domain-navigation fixed inset-x-0 bottom-0 z-40 border-t border-border bg-background px-2 pb-[env(safe-area-inset-bottom)] shadow-2 lg:static lg:z-auto lg:min-w-0 lg:border-0 lg:bg-transparent lg:p-0 lg:shadow-none">
    <div role="tablist" aria-label="Chọn nội dung" onKeyDown={event=>{
      const keys=['ArrowLeft','ArrowRight','Home','End'];if(!keys.includes(event.key))return
      const tabs=[...event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]:not(:disabled)')]
      const index=tabs.indexOf(document.activeElement as HTMLButtonElement)
      const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length
      event.preventDefault();tabs[next]?.focus();tabs[next]?.click()
    }} className="grid grid-cols-5 gap-1 lg:flex lg:justify-center">
      {screens.map(({id,label,icon:Icon})=><Button key={id} role="tab" aria-selected={current===id} aria-controls="app-domain-panel" tabIndex={focusTab===id?0:-1} disabled={id==='mimi'&&!mimiAvailable} title={id==='mimi'&&!mimiAvailable?'Mimi chưa bật trong phiên này':undefined} size="lg" variant={current===id?'selected':'ghost'} className="h-auto min-h-14 min-w-0 flex-col gap-1 px-1 py-2 text-xs lg:min-h-12 lg:px-2 xl:px-3" onClick={()=>onSelect(id)}><Icon className="size-5" aria-hidden="true"/><span className="max-w-full whitespace-normal">{label}</span></Button>)}
    </div>
  </nav>
}

export function ApplicationMenu({current,mimiAvailable,gardenAvailable,onSelect,onChat,onPin,onHome,onSubscription,onLogout,loggingOut}:{current:AppScreen|null;mimiAvailable:boolean;gardenAvailable:boolean;onSelect:(screen:AppScreen)=>void;onChat:()=>void;onPin:()=>void;onHome:()=>void;onSubscription:()=>void;onLogout:()=>void;loggingOut:boolean}) {
  const [open,setOpen]=useState(false)
  const trigger=useRef<HTMLButtonElement>(null)
  const afterClose=useRef<(()=>void)|null>(null)
  function choose(action:()=>void){afterClose.current=action;setOpen(false)}
  return <>
    <Button ref={trigger} data-testid="app-menu-open" type="button" variant="ghost" size="icon-lg" className="size-11 shrink-0" aria-label="Ứng dụng" aria-expanded={open} onClick={()=>setOpen(true)}><Grid2X2 aria-hidden="true"/></Button>
    <Dialog open={open} onOpenChange={setOpen}><DialogContent data-testid="app-menu" className="bottom-0 left-0 right-0 top-auto max-h-[85dvh] w-full max-w-none translate-x-0 translate-y-0 overflow-y-auto rounded-b-none rounded-t-2xl p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] lg:bottom-auto lg:left-auto lg:right-6 lg:top-20 lg:w-80 lg:max-w-sm lg:rounded-xl lg:pb-4" onCloseAutoFocus={event=>{event.preventDefault();trigger.current?.focus();const action=afterClose.current;afterClose.current=null;if(action)queueMicrotask(action)}}>
      <DialogHeader><DialogTitle>Ứng dụng</DialogTitle><DialogDescription>Đi tới nội dung và tuỳ chọn của microSched.</DialogDescription></DialogHeader>
      <div className="grid gap-1">
        {APP_SCREENS.map(({id,label,icon:Icon})=>{
          const unavailable = id==='migarden' && !gardenAvailable
          return <Button key={id} type="button" data-testid={id==='migarden'?(unavailable?'migarden-placeholder':'migarden-open'):undefined}
            variant={current===id?'selected':'ghost'} disabled={unavailable || id==='mimi'&&!mimiAvailable}
            className="h-auto min-h-11 justify-start gap-3 whitespace-normal text-left" onClick={()=>choose(()=>onSelect(id))}>
            <Icon className="size-5 shrink-0" aria-hidden="true"/><span className="flex-1">{label}</span>
            {unavailable?<Badge variant="secondary">Sắp có</Badge>:<ChevronRight className="size-4" aria-hidden="true"/>}
          </Button>
        })}
      </div>
      <div className="grid gap-1 border-t pt-3">
        {mimiAvailable?<Button data-testid="mimi-dock-open" aria-controls="mimi-side-chat" variant="ghost" className="min-h-11 justify-start gap-3" onClick={()=>choose(onChat)}><MessagesSquare aria-hidden="true"/>Chat với Mimi</Button>:null}
        <Button asChild variant="ghost" className="min-h-11 justify-start gap-3"><a href="/subscription" data-testid="app-subscriptions-link" onClick={event=>{if(event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;event.preventDefault();choose(onSubscription)}}><CreditCard aria-hidden="true"/>Đăng ký định kỳ</a></Button>
        <Button data-testid="private-pin-change-open" variant="ghost" className="min-h-11 justify-start gap-3" onClick={()=>choose(onPin)}><KeyRound aria-hidden="true"/>Đổi PIN riêng tư</Button>
        <Button asChild variant="ghost" className="min-h-11 justify-start gap-3"><a href="/home" data-testid="app-homepage-link" onClick={event=>{if(event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;event.preventDefault();choose(onHome)}}><BookOpen aria-hidden="true"/>Giới thiệu microSched</a></Button>
        <Button variant="ghost" disabled={loggingOut} className="min-h-11 justify-start gap-3" onClick={()=>choose(onLogout)}><LogOut aria-hidden="true"/>Đăng xuất</Button>
      </div>
    </DialogContent></Dialog>
  </>
}
