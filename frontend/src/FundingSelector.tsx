import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { apiRequest } from '@/api'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { known, unlocked } from '@/outbox/core'
import { useOutbox } from '@/outbox/view'

import { sourceLabel, type FundingSource, type Funding } from '@/funding-ui'

export function FundingSelector({value,onChange,current,disabled=false}:{value:string;onChange:(id:string)=>void;current?:Funding|null;disabled?:boolean}) {
  const state=useOutbox()
  const selectedPrivate=useRef(false)
  const [cursor,setCursor]=useState<string|null>(null)
  const [prior,setPrior]=useState<FundingSource[]>([])
  const query=useQuery({queryKey:['tracker','funding-candidates',cursor],queryFn:()=>apiRequest<{items:FundingSource[];next_cursor:string|null}>('/api/tracker/funding-candidates'+(cursor?'?cursor='+encodeURIComponent(cursor):'')),retry:false})
  const pending:FundingSource[]=[]
  for(const row of state.rows){
    if(row.invalid||row.principal!==state.context.principal||row.kind!=='entry.create'||['held','rejected'].includes(row.state))continue
    const tracker=known('tracker',row.parent)
    if(!tracker||tracker.direction!=='in'||tracker.is_private!==false&&!unlocked())continue
    const body=JSON.parse(row.payload)
    if(typeof body.amount==='number')pending.push({id:row.entity,tracker_id:row.parent,tracker_name:String(tracker.name),amount:body.amount,occurred_at:body.occurred_at,is_private:tracker.is_private!==false,pending:true})
  }
  const options=[...new Map([...pending,...prior,...(query.data?.items??[]),...(current?.status==='available'?[current.source]:[])].filter(s=>!s.is_private||unlocked()).map(s=>[s.id,s])).values()]
  function select(id:string) {
    // Remember the user's intent before synchronous cache masking removes its metadata.
    selectedPrivate.current=options.some(s=>s.id===id&&s.is_private)
    onChange(id)
  }
  useEffect(()=>{
    const mask=()=>{setPrior([]);setCursor(null);if(!unlocked()&&selectedPrivate.current){selectedPrivate.current=false;onChange(current?'keep':'locked')}}
    window.addEventListener('microsched:visibility',mask)
    return()=>window.removeEventListener('microsched:visibility',mask)
  },[current,onChange])
  const unavailableWhileLocked=!unlocked()&&!['none','keep','locked'].includes(value)&&!options.some(s=>s.id===value&&!s.is_private)
  // A lock can synchronously replace query metadata before the visibility listener runs.
  // Preserve the public draft, but require an explicit safe selection before a new save.
  useEffect(()=>{
    if(unavailableWhileLocked)onChange(current?'keep':'locked')
  },[unavailableWhileLocked,current,onChange])
  const safeValue=options.some(s=>s.id===value)||['none','keep','locked'].includes(value)?value:'locked'
  return <div className="space-y-1.5" data-testid="funding-selector">
    <label className="block text-sm font-semibold">Nguồn thu (không bắt buộc)
      <Select value={safeValue} onValueChange={select} disabled={disabled}>
        <SelectTrigger size="lg" aria-label="Nguồn thu (không bắt buộc)" className="mt-1 min-h-11 w-full text-left"><SelectValue/></SelectTrigger>
        <SelectContent><SelectItem value="none" className="min-h-11">Không gắn nguồn thu</SelectItem>
          {current||safeValue==='keep'?<SelectItem value="keep" className="min-h-11">{current?.status==='available' && (!current.source.is_private || unlocked()) ? sourceLabel(current.source) : current?.status==='none' ? 'Không gắn nguồn thu (hiện tại)' : 'Giữ liên kết hiện tại / nguồn chưa khả dụng'}</SelectItem>:null}
          {safeValue==='locked'?<SelectItem value="locked" className="min-h-11">Chọn lại nguồn thu để tiếp tục</SelectItem>:null}
          {options.map(s=><SelectItem key={s.id} value={s.id} className="min-h-11 max-w-[85vw] whitespace-normal break-words">{sourceLabel(s)}</SelectItem>)}
        </SelectContent>
      </Select>
    </label>
    {safeValue==="locked"?<p role="status" className="text-sm text-muted-foreground">Chọn nguồn thu công khai, chọn “Không gắn nguồn thu” hoặc mở khoá để chọn lại. Nội dung đang nhập vẫn được giữ.</p>:null}
    {query.isError?<p role="status" className="text-sm text-muted-foreground">Chưa tải được nguồn thu. Nội dung đang nhập vẫn được giữ.</p>:null}
    {query.data?.next_cursor?<Button type="button" variant="ghost" className="min-h-11" onClick={()=>{setPrior(options);setCursor(query.data!.next_cursor)}}>Nguồn thu cũ hơn</Button>:null}
  </div>
}
