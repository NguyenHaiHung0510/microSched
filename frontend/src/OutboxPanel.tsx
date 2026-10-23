import { useState } from 'react'
import { Activity, CloudUpload, ListTodo, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { discardRejected, effectivePrivate, known, retry, unlocked } from '@/outbox/core'
import { useOutbox, useDerivedPending } from '@/outbox/view'
import { snapshotAt } from '@/outbox/public-cache'
import type { Fields } from '@/outbox/protocol'

export function OutboxPanel() {
  const state=useOutbox(),[open,setOpen]=useState(false),[discard,setDiscard]=useState<string|null>(null),[error,setError]=useState('')
  const rows=state.rows.filter(r => r.principal===state.context.principal)
  return <>
    {(rows.length>0||state.error) && <Button data-testid="outbox-trigger" variant="selected" size="lg" onClick={() => setOpen(true)}>
      <CloudUpload />{rows.length} đang chờ gửi
    </Button>}
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent data-testid="outbox-panel" className="left-auto right-0 top-0 flex h-dvh max-h-dvh w-full max-w-full translate-x-0 translate-y-0 flex-col rounded-none border-0 p-5 sm:max-w-md"
        onCloseAutoFocus={event => {
          event.preventDefault()
          const target=document.querySelector<HTMLButtonElement>('[data-testid="outbox-trigger"]')??document.querySelector<HTMLButtonElement>('header button')
          target?.focus()
        }}>
        <DialogHeader><DialogTitle>Thay đổi đang chờ</DialogTitle>
          <DialogDescription>Đã lưu cục bộ chưa có nghĩa đã gửi tới máy chủ. Gửi xong sẽ tự rời danh sách.</DialogDescription>
        </DialogHeader>
        {state.error && <p role="alert" className="text-sm text-bad">{state.error}</p>}
        <p role="status" className="text-sm text-muted-foreground">{state.capability}</p>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
          {rows.length===0 && <p role="status">Đã gửi hết</p>}
          {rows.map(row => {
            const hidden=row.invalid || effectivePrivate(row)&&!unlocked(),p=hidden?{}:JSON.parse(row.payload) as Fields
            const task=row.kind.startsWith('task'),parent=known(task?'task':'tracker',row.parent)
            const label=row.invalid?'Lệnh cần kiểm tra định dạng':hidden?'Thay đổi riêng tư':String(p.title??parent?.[task?'title':'name']??(task?'Task':'Bản ghi'))
            const status=row.state==='rejected'?'Chưa gửi được · Nội dung cần kiểm tra':
              row.reason||(!navigator.onLine?'Chờ kết nối':row.state==='sending'?'Đang gửi':'Đang chờ gửi')
            return <div key={row.id} data-testid="outbox-row" className="flex min-w-0 items-start gap-3 rounded-xl border border-border bg-card p-4 shadow-1">
              {task?<ListTodo className="mt-1 size-5 shrink-0 text-primary" />:<Activity className="mt-1 size-5 shrink-0 text-primary" />}
              <div className="min-w-0 flex-1 space-y-2"><p className="break-words text-sm font-bold">{label}</p>
                <p className="text-sm text-muted-foreground">{row.invalid?'Định dạng/toàn vẹn chưa hỗ trợ; đang giữ nguyên lệnh':hidden?'Cần mở khoá để xem và gửi':status}</p>
                {row.state==='rejected' && <Button variant="outline" size="lg" onClick={() => setDiscard(row.id)}>Bỏ thay đổi</Button>}
              </div>
            </div>
          })}
        </div>
        {(error||state.reconciling.length>0)&&<p role="status" className="text-sm text-muted-foreground">{error||'Đang đối chiếu dữ liệu vừa gửi…'}</p>}
        {rows.length>0 && <Button variant="outline" size="lg" onClick={() => void retry().catch(() => setError('Chưa đọc được hàng đợi. Giữ thay đổi.'))}><RefreshCw />Thử kết nối lại</Button>}
      </DialogContent>
    </Dialog>
    <Dialog open={discard!==null} onOpenChange={v => {if(!v)setDiscard(null)}}>
      <DialogContent><DialogHeader><DialogTitle>Bỏ thay đổi chưa được áp dụng?</DialogTitle>
        <DialogDescription>Chỉ bỏ lệnh bị từ chối và các thay đổi thực sự phụ thuộc vào nó. Những thay đổi độc lập được giữ.</DialogDescription></DialogHeader>
        <Button variant="destructive" size="lg" onClick={() => {if(discard)void discardRejected(discard).then(() => setDiscard(null)).catch(() => setError('Không thể bỏ lệnh chưa rõ kết quả.'))}}>Bỏ thay đổi</Button>
        <Button variant="outline" size="lg" onClick={() => setDiscard(null)}>Giữ lại</Button>
      </DialogContent>
    </Dialog>
  </>
}
export function OfflineCoverage() {
  const state=useOutbox()
  if(navigator.onLine&&!state.context.principal)return null
  return !navigator.onLine?<p role="status" data-testid="offline-coverage" className="text-sm text-muted-foreground">
    Đang ngoại tuyến · Dữ liệu đã tải chỉ một phần{snapshotAt?' · '+new Date(snapshotAt).toLocaleString('vi-VN'):''}. Đăng nhập/mở khoá và các phần chưa hỗ trợ cần kết nối.
  </p>:null
}
export function DerivedPendingNotice() {
  return useDerivedPending()?<p role="status" data-testid="derived-pending" className="rounded-lg bg-warn-bg p-3 text-sm text-warn">
    Đang chờ cập nhật · Biểu đồ/báo cáo là lần xác nhận cuối; các bản ghi đang chờ chưa phải tổng đã đối chiếu.
  </p>:null
}
