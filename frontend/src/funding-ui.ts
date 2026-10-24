import { formatVnd } from '@/tracker-ui'

export type FundingSource = {id:string;tracker_id:string;tracker_name:string;occurred_at:string;amount:number;is_private:boolean;pending?:boolean}
export type Funding = {status:'none'|'unavailable'} | {status:'available';source:FundingSource}
export const sourceLabel=(s:FundingSource)=>`${s.tracker_name} · ${new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}).format(new Date(s.occurred_at))} · ${formatVnd(s.amount)}${s.pending?' · đang chờ':''}`
