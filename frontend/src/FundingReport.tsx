import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { apiRequest } from '@/api'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { sourceLabel, type FundingSource } from '@/funding-ui'
import { useDerivedPending } from '@/outbox/view'
import { formatVnd } from '@/tracker-ui'

type Bucket={key:string;source:FundingSource|null;total:number;count:number;trackers:{tracker_id:string;name:string;total:number;count:number}[];expenses:{id:string;tracker_name:string;occurred_at:string;amount:number}[];has_more:boolean}
type Report={expense_total:number;income_total:number;net:number;corrupted_entry_count:number;buckets:Bucket[]}
export function FundingReport({month,months,onOpenSource}:{month:string;months:number;onOpenSource:(source:FundingSource)=>void}){
  const query=useQuery({queryKey:['tracker','funding-report',month,months],queryFn:()=>apiRequest<Report>(`/api/tracker/funding-report?month=${month}&months=${months}`),retry:false})
  const [selected,setSelected]=useState<string|null>(null)
  const [maskedAt,setMaskedAt]=useState(0)
  const pending=useDerivedPending()
  useEffect(()=>{const mask=()=>{setSelected(null);setMaskedAt(Date.now())};window.addEventListener('microsched:visibility',mask);return()=>window.removeEventListener('microsched:visibility',mask)},[])
  const data=query.dataUpdatedAt>maskedAt?query.data:undefined
  const bucket=data?.buckets.find(b=>b.key===selected)
  const label=(b:Bucket)=>b.source?sourceLabel(b.source):b.key==='unlinked'?'Chưa gắn nguồn':'Nguồn không còn khả dụng'
  return <Card className="gap-3 p-4" data-testid="funding-report">
    <h3 className="text-base font-bold">Chi theo nguồn thu</h3>
    {pending?<p role="status" className="text-sm text-muted-foreground">Có bản ghi đang chờ đồng bộ. Báo cáo chỉ gồm khoản đã được máy chủ xác nhận.</p>:null}
    {!data?<p role="status" className="text-sm text-muted-foreground">{query.isError?'Chưa tải được báo cáo nguồn thu. Hãy thử lại khi có mạng.':'Đang tải báo cáo…'}</p>:<>
      <p className="text-sm">Tổng chi: <strong className="tabular-nums">{formatVnd(data.expense_total)}</strong></p>
      {data.corrupted_entry_count?<p role="status" className="text-sm text-bad">Có bản ghi chưa đọc được số tiền; báo cáo có thể chưa đầy đủ.</p>:null}
      {data.buckets.length===0?<p className="text-sm text-muted-foreground">Chưa có khoản chi trong khoảng này.</p>:null}
      {data.buckets.map(b=><Button key={b.key} type="button" variant={selected===b.key?'selected':'ghost'} className="h-auto min-h-11 w-full flex-wrap justify-between gap-2 whitespace-normal py-2 text-left" onClick={()=>setSelected(b.key)} data-testid="funding-bucket" data-bucket={b.key} aria-pressed={selected===b.key}>
        <span className="min-w-0 flex-1 break-words">{label(b)}</span><span className="tabular-nums">{formatVnd(b.total)} · {b.count} khoản chi</span>
        <span className="h-2 w-full rounded bg-accent" aria-hidden="true"><span className="block h-2 rounded bg-primary" style={{width:`${data.expense_total?b.total/data.expense_total*100:0}%`}}/></span>
      </Button>)}
      {bucket?<section className="space-y-2 rounded-lg border p-3" aria-label="Chi tiết nguồn thu">
        <h4 className="break-words text-sm font-bold">{label(bucket)}</h4>{bucket.source?<Button type="button" variant="outline" className="min-h-11" onClick={()=>onOpenSource(bucket.source!)}>Xem bản ghi nguồn thu</Button>:null}
        {bucket.trackers.map(t=><p key={t.tracker_id} className="flex flex-wrap justify-between gap-2 text-sm"><span className="min-w-0 break-words">{t.name} · {t.count} khoản</span><strong className="tabular-nums">{formatVnd(t.total)}</strong></p>)}
        <details><summary className="min-h-11 cursor-pointer py-3 text-sm">Các khoản chi gần nhất</summary>{bucket.expenses.map(e=><p key={e.id} className="break-words py-1 text-sm">{new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}).format(new Date(e.occurred_at))} · {e.tracker_name} · {formatVnd(e.amount)}</p>)}{bucket.has_more?<p className="text-sm text-muted-foreground">Đang hiển thị 50 khoản gần nhất; tổng và phân nhóm gồm toàn bộ.</p>:null}</details>
      </section>:null}
    </>}
    {query.isError?<Button type="button" variant="outline" className="min-h-11" onClick={()=>void query.refetch()}>Thử lại</Button>:null}
  </Card>
}
