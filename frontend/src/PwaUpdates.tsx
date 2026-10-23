import { useEffect, useRef, useState } from 'react'
import { registerSW } from 'virtual:pwa-register'
import { Button } from '@/components/ui/button'
import { useOutbox } from '@/outbox/view'
import { getSnapshot } from '@/outbox/core'

function formValue(form: HTMLFormElement): string {
  return JSON.stringify([...form.querySelectorAll('input,textarea,select,[role="checkbox"],[role="combobox"]')].map(element => {
    if(element instanceof HTMLInputElement) return [element.name,element.type,['checkbox','radio'].includes(element.type)?element.checked:element.value]
    if(element instanceof HTMLTextAreaElement||element instanceof HTMLSelectElement)return [element.name,element.value]
    return [element.getAttribute('role'),element.getAttribute('aria-checked'),element.textContent]
  }))
}
export function PwaUpdates() {
  const state=useOutbox(),[waiting,setWaiting]=useState(false),[message,setMessage]=useState('')
  const [update,setUpdate]=useState<((reload?:boolean)=>Promise<void>)|null>(null)
  const [drafts]=useState(() => new Map<HTMLFormElement,string>())
  const reloadApproved=useRef(false), activatedUpdate=useRef(false)
  useEffect(() => {
    const capture=(event:Event) => {
      const form=event.target instanceof Element?event.target.closest('form'):null
      if(form&&!drafts.has(form))drafts.set(form,formValue(form))
    }
    const clear=() => drafts.clear()
    document.addEventListener('focusin',capture,true)
    window.addEventListener('microsched:visibility',clear)
    const dirty=() => [...drafts].some(([form,initial]) => form.isConnected&&formValue(form)!==initial)
    const reload=() => {
      if(!reloadApproved.current)return
      reloadApproved.current=false
      if(dirty()||getSnapshot().admitting>0||getSnapshot().error){setMessage('Còn thay đổi chưa lưu. Giữ phiên này; cập nhật khi đã lưu nháp.');return}
      window.location.reload()
    }
    let controller=navigator.serviceWorker?.controller
    const controlled=() => {
      const next=navigator.serviceWorker.controller
      if(controller&&next!==controller){activatedUpdate.current=true;setWaiting(true)}
      controller=next
      reload()
    }
    navigator.serviceWorker?.addEventListener('controllerchange',controlled)
    // Workbox can classify a quick/external update without isUpdate. Reload only
    // this page's explicit, rechecked request; other tabs retain their drafts.
    const apply=registerSW({immediate:true,onNeedRefresh:() => setWaiting(true),onNeedReload:reload})
    queueMicrotask(() => setUpdate(() => apply))
    return () => {
      document.removeEventListener('focusin',capture,true)
      window.removeEventListener('microsched:visibility',clear)
      navigator.serviceWorker?.removeEventListener('controllerchange',controlled)
    }
  },[drafts])
  if(!waiting)return null
  return <div role="status" data-testid="pwa-update" data-app-generation={import.meta.env.VITE_APP_GENERATION??'v1'} className="my-2 rounded-xl bg-warn-bg p-3 text-sm">
    <p>Có phiên bản mới. Hàng đợi V1 được giữ qua cập nhật.</p>
    {message&&<p>{message}</p>}
    <Button variant="outline" size="lg" className="mt-2" onClick={() => {
      const dirty=[...drafts].some(([form,initial]) => form.isConnected&&formValue(form)!==initial)
      if(dirty){setMessage('Còn nội dung chưa lưu. Lưu hoặc đóng bản nháp trước khi cập nhật.');return}
      if(state.admitting>0){setMessage('Đang lưu cục bộ. Đợi lưu xong trước khi cập nhật.');return}
      if(state.error){setMessage('Chưa xác minh được bộ nhớ. Giữ phiên này để bảo toàn thay đổi.');return}
      reloadApproved.current=true
      if(activatedUpdate.current){window.location.reload();return}
      void update?.(false).catch(() => {reloadApproved.current=false;setMessage('Chưa cập nhật được. Giữ phiên này và thử lại.')})
    }}>Cập nhật khi đã lưu nháp</Button>
  </div>
}
