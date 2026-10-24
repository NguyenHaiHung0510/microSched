import { useEffect, useMemo, useRef, useState } from 'react';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Check, ExternalLink, Filter, Info, LockKeyhole, RefreshCw } from 'lucide-react';
import { apiRequest } from '@/api';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { PrivateMarker } from '@/PrivateMarker';
import { ReminderSourceDialog } from '@/ReminderSourceDialog';
import type { ReminderSource } from '@/reminder-ui';
import { useOutbox } from '@/outbox/view';
import { barrier, getSnapshot } from '@/outbox/core';
import { uuidv7 } from '@/lib/uuidv7';
import { navigate } from '@/lib/route';
import { selectMimiConversation } from '@/mimi-selection';
import { historyDay, historyIdentity, historyStatus, historyTime, type HistoryRow, type HistoryPage, type HistoryBatch } from '@/reminder-history';
const sources = [['all', 'Tất cả nguồn'], ['task', 'Task'], ['event', 'Buổi'], ['annotation', 'Dấu ngày'], ['tracker', 'Tracker'], ['subscription', 'Đăng ký'], ['mimi', 'Mimi']];
const originLabel: Record<string, string> = { one_shot: 'Một lần', tracker_dispatch: 'Tracker định kỳ', subscription_dispatch: 'Gia hạn đăng ký', mimi_intent: 'Mimi' };
export function ReminderHistory() {
    const client = useQueryClient(), state = useOutbox();
    const [epoch, setEpoch] = useState(0), [source, setSource] = useState('all'), [status, setStatus] = useState('all'), [handled, setHandled] = useState('all');
    const [from, setFrom] = useState(''), [to, setTo] = useState(''), [selected, setSelected] = useState<string[]>([]);
    const [filtersOpen,setFiltersOpen]=useState(false),[selectionMode,setSelectionMode]=useState(false);
    const [batch, setBatch] = useState<HistoryBatch | null>(null), [message, setMessage] = useState(''), [opened, setOpened] = useState<HistoryRow | null>(null);
    const gate = useRef(0), replayId = useRef<string | null>(null), replayScope = useRef('');
    const filter = useMemo(() => ({ ...(source === 'all' ? {} : { source }), ...(status === 'all' ? {} : { status }), handled, ...(from ? { day_from: from } : {}), ...(to ? { day_to: to } : {}) }), [source, status, handled, from, to]);
    const filterKey = JSON.stringify(filter);
    function changeFilter(change: () => void) { gate.current++; setSelected([]); setBatch(null); setMessage(''); replayId.current = null; change(); }
    const rows = useInfiniteQuery({
        queryKey: ['reminder-history', state.context.principal, state.context.privateUntil > 0, epoch, filterKey], initialPageParam: '',
        queryFn: async ({ pageParam, signal }) => { const openedGate = gate.current; const q = new URLSearchParams({ ...filter, limit: '50', ...(pageParam ? { cursor: pageParam } : {}) }); const data = await apiRequest<HistoryPage>('/api/reminder-history?' + q, { signal }); if (openedGate !== gate.current)
            throw new Error('Phạm vi đã đổi; tải lại lịch sử.');
            if (getSnapshot().context.privateUntil <= Date.now() && data.items.some(row => row.is_private))
                return {...data,items:data.items.filter(row=>!row.is_private),next_cursor:null,has_more:false,
                    private_notice:{title:'Nhắc việc riêng tư',body:'Nội dung được ẩn'}};
            return data; },
        getNextPageParam: page => page.next_cursor ?? undefined, retry: false, refetchOnWindowFocus: false, gcTime: 0,
    });
    const items = [...new Map((rows.data?.pages.flatMap(p => p.items) ?? []).map(r => [historyIdentity(r), r])).values()];
    const groups = new Map<string, HistoryRow[]>();
    for (const row of items) {
        const day = row.occurrence_on ?? '';
        groups.set(day, [...(groups.get(day) ?? []), row]);
    }
    const refresh = () => { setSelected([]); setBatch(null); replayId.current = null; client.removeQueries({ queryKey: ['reminder-history'] }); setEpoch(x => x + 1); };
    async function queueBarrier(row?: Pick<HistoryRow, 'source_ref'>) {
        if (!navigator.onLine)
            throw new Error('Cần kết nối để xác nhận đã xử lý; chưa lưu thay đổi.');
        if (row && row.source_ref.kind !== 'subscription') {
            const kind = row.source_ref.kind;
            if (kind === 'task' || kind === 'tracker')
                await barrier(kind + ':' + row.source_ref.id);
            return;
        }
        // A whole-filter selection cannot safely count a relevant local pending source.
        const pending = getSnapshot().rows.filter(r => r.principal === getSnapshot().context.principal);
        for (const command of pending) {
            const kind = command.kind.startsWith('task') ? 'task' : 'tracker';
            if (source === 'all' || source === kind || source === 'subscription' && kind === 'tracker')
                await barrier(command.aggregate);
        }
    }
    const mark = useMutation({ networkMode: 'always', mutationFn: async (row: Pick<HistoryRow,'occurrence_ref'|'source_ref'>) => { const g = gate.current; await queueBarrier(row); await apiRequest('/api/reminder-history/' + row.occurrence_ref.origin + '/' + row.occurrence_ref.id + '/handled', { method: 'PUT', body: JSON.stringify({ handled: true }) }); if (g !== gate.current)
            throw new Error('Phạm vi đã đổi; tải lại để xem trạng thái hiện tại.'); },
        onSuccess: () => { setMessage('Đã xử lý lần nhắc.'); refresh(); }, onError: e => setMessage(e.message) });
    const prepare = useMutation({ networkMode: 'always', mutationFn: async (mode: 'all' | 'selected') => { const g = gate.current; await queueBarrier(); const selected_refs = mode === 'selected' ? items.filter(r => selected.includes(historyIdentity(r))).map(r => r.occurrence_ref) : undefined; const scope=JSON.stringify({filter,selected_refs}); if(scope!==replayScope.current){replayId.current=null;replayScope.current=scope} replayId.current ??= uuidv7(); const result = await apiRequest<HistoryBatch>('/api/reminder-history/handled-batches/prepare', { method: 'POST', body: JSON.stringify({ batch_id: replayId.current, filter, selected_refs }) }); if (g !== gate.current)
            throw new Error('Phạm vi đã đổi; chuẩn bị lựa chọn mới.'); return result; }, onSuccess: setBatch, onError: e => setMessage(e.message) });
    const commit = useMutation({ networkMode: 'always', mutationFn: async () => { if (!batch)
            throw new Error('Chọn lại phạm vi.'); const g = gate.current; await queueBarrier(); const result = await apiRequest<HistoryBatch>('/api/reminder-history/handled-batches/' + batch.id + '/commit', { method: 'POST', body: '{}' }); if (g !== gate.current)
            throw new Error('Phạm vi đã đổi; tải lại lịch sử.'); return result; }, onSuccess: r => { setMessage(r.scope_visible ? 'Đã xử lý ' + r.result?.selected_count + ' lần nhắc.' : 'Đã xác nhận thao tác trước; nội dung hiện không còn hiển thị.'); refresh(); }, onError: e => setMessage(e.message) });
    const {reset:resetMark}=mark, {reset:resetPrepare}=prepare, {reset:resetCommit}=commit;
    useEffect(() => {
        const purge = () => { resetMark(); resetPrepare(); resetCommit(); gate.current++; setEpoch(x => x + 1); setSelected([]); setBatch(null); setOpened(row => row?.is_private ? null : row); setMessage(''); replayId.current = null; void client.cancelQueries({ queryKey: ['reminder-history'] }); client.removeQueries({ queryKey: ['reminder-history'] }); };
        window.addEventListener('microsched:visibility', purge);
        window.addEventListener('microsched:auth-lost', purge);
        return () => { window.removeEventListener('microsched:visibility', purge); window.removeEventListener('microsched:auth-lost', purge); client.removeQueries({ queryKey: ['reminder-history'] }); };
    }, [client, resetMark, resetPrepare, resetCommit]);
    function open(row: HistoryRow) { if (row.source_kind === 'mimi') {
        selectMimiConversation(row.source_ref.id);
        navigate('/mimi');
    }
    else if (row.source_kind === 'subscription')
        navigate('/subscription');
    else
        setOpened(row); }
    return <section data-testid="reminder-history" className="min-w-0 space-y-4">
  <div className="space-y-1"><h3 className="text-base font-bold">Lịch sử nhắc</h3><p className="text-xs text-muted-foreground">Gần nhất trước · Xử lý lần nhắc, không hoàn thành công việc.</p></div>
  <div className="grid min-w-0 grid-cols-2 items-center gap-2">
   <Select value={source} onValueChange={v => changeFilter(() => setSource(v))}><SelectTrigger className="col-span-2 min-h-11 w-full sm:col-span-1" aria-label="Nguồn lịch sử"><SelectValue /></SelectTrigger><SelectContent>{sources.map(([v, label]) => <SelectItem key={v} value={v}>{label}</SelectItem>)}</SelectContent></Select>
   <Select value={handled} onValueChange={v => changeFilter(() => setHandled(v))}><SelectTrigger className="min-h-11 w-full" aria-label="Trạng thái xử lý"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Tất cả xử lý</SelectItem><SelectItem value="unhandled">Chưa xử lý</SelectItem><SelectItem value="handled">Đã xử lý</SelectItem></SelectContent></Select>
   <div className="flex items-center justify-end gap-1"><Button data-testid="history-filters-toggle" size="lg" variant="outline" aria-expanded={filtersOpen} aria-controls="history-filters" onClick={()=>setFiltersOpen(open=>!open)}><Filter aria-hidden="true"/>Lọc{status!=='all'||from||to?' · Đang lọc':''}</Button><Button size="icon-lg" variant="ghost" aria-label="Làm mới lịch sử" onClick={refresh}><RefreshCw aria-hidden="true"/></Button></div>
  </div>
  <div id="history-filters" hidden={!filtersOpen} className="grid min-w-0 gap-2 rounded-lg border p-3 sm:grid-cols-2">
   <Select value={status} onValueChange={v => changeFilter(() => setStatus(v))}><SelectTrigger className="min-h-11 w-full" aria-label="Trạng thái gửi"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Mọi trạng thái gửi</SelectItem>{Object.entries(historyStatus).map(([v, label]) => <SelectItem key={v} value={v}>{label}</SelectItem>)}</SelectContent></Select>
   <Button size="lg" variant="ghost" onClick={()=>changeFilter(()=>{setStatus('all');setFrom('');setTo('')})}>Đặt lại lọc nâng cao</Button>
   <label className="space-y-1 text-sm">Từ ngày<Input name="history-from" type="date" value={from} onChange={e => changeFilter(() => setFrom(e.target.value))} className="min-h-11"/></label>
   <label className="space-y-1 text-sm">Đến ngày<Input name="history-to" type="date" value={to} onChange={e => changeFilter(() => setTo(e.target.value))} className="min-h-11"/></label>
  </div>
  <div className="flex flex-wrap items-start justify-between gap-2">{rows.data?.pages[0].private_notice && <p className="flex min-h-11 items-center gap-1 text-xs text-muted-foreground"><LockKeyhole aria-hidden="true" className="size-4"/>Nhắc riêng tư được ẩn</p>}
  <details className="text-xs text-muted-foreground"><summary className="flex min-h-11 cursor-pointer items-center gap-2"><Info aria-hidden="true" className="size-4"/>Về lịch sử</summary><p className="max-w-sm pb-2">Chỉ gồm các lần nhắc còn bản ghi. Nội dung đối tượng là hiện tại; giờ gửi hoặc lịch sử cũ không được lưu sẽ không suy đoán.</p></details></div>
  {message && <p role="status" aria-live="polite" className="break-words text-sm">{message}</p>}
  {rows.isPending ? <p role="status">Đang tải lịch sử…</p> : rows.isError ? <p role="alert">Chưa tải được lịch sử. Làm mới để thử lại.</p> : items.length === 0 ? <p className="text-sm text-muted-foreground">Chưa có lần nhắc phù hợp.</p> : null}
  {[...groups].map(([day, dayRows]) => <section key={day} className="space-y-2" aria-label={historyDay(day)}><h4 className="border-b pb-2 text-sm font-bold">{historyDay(day)}</h4>{dayRows.map(row => {
                const id = historyIdentity(row), pending = mark.isPending && mark.variables?.occurrence_ref.id === row.occurrence_ref.id;
                return <article key={id} data-testid="history-row" data-occurrence={id} className="min-w-0 space-y-2 rounded-lg border p-3 [content-visibility:auto]">
   <div className="flex min-w-0 items-start gap-2">{selectionMode?<label className="flex min-h-11 min-w-11 items-center justify-center"><Checkbox aria-label={'Chọn ' + row.title} checked={selected.includes(id)} disabled={!!row.handled_at} onCheckedChange={v => { replayId.current = null; setSelected(s => v ? [...new Set([...s, id])] : s.filter(x => x !== id)); }}/></label>:null}<div className="min-w-0 flex-1"><p className="break-words font-semibold">{row.title}</p><p className="text-xs text-muted-foreground">{originLabel[row.origin]} · {historyTime(row)}</p></div>{row.is_private && <PrivateMarker />}</div>
   {row.body?<details className="group/history-body text-sm"><summary className="min-h-11 cursor-pointer list-none py-1"><span className="line-clamp-2 whitespace-pre-wrap [overflow-wrap:anywhere] group-open/history-body:hidden">{row.body}</span><span className="text-xs font-semibold text-primary"><span className="group-open/history-body:hidden">Xem đầy đủ</span><span className="hidden group-open/history-body:inline">Thu gọn</span></span></summary><p className="whitespace-pre-wrap [overflow-wrap:anywhere]">{row.body}</p></details>:null}
   <p className="text-xs text-muted-foreground">{historyStatus[row.status] ?? row.status}{row.handled_at ? ' · Đã xử lý' : ''}</p>
   <div className="flex flex-wrap gap-2"><Button data-testid="history-handle" size="lg" variant={row.handled_at ? 'ghost' : 'outline'} disabled={!!row.handled_at || mark.isPending || prepare.isPending || commit.isPending} onClick={() => mark.mutate({occurrence_ref:row.occurrence_ref,source_ref:row.source_ref})}><Check aria-hidden="true"/>{pending ? 'Đang xác nhận…' : row.handled_at ? 'Đã xử lý' : 'Đánh dấu đã xử lý'}</Button>{row.can_open && <Button size="lg" variant="ghost" onClick={() => open(row)}><ExternalLink aria-hidden="true"/>Mở đối tượng</Button>}</div>
  </article>;
            })}</section>)}
  <div className="flex flex-wrap items-center gap-2">
   <Button data-testid="history-selection-toggle" size="lg" variant="outline" disabled={prepare.isPending||commit.isPending} aria-pressed={selectionMode} onClick={()=>{setSelectionMode(value=>!value);setSelected([]);setBatch(null);replayId.current=null}}>{selectionMode?'Huỷ chọn nhiều':'Chọn nhiều'}</Button>
   {selectionMode?<><Button size="lg" variant="outline" disabled={!selected.length || prepare.isPending} onClick={() => prepare.mutate('selected')}>{prepare.isPending ? 'Đang đếm…' : 'Xử lý ' + selected.length + ' đã chọn'}</Button>
   <Button data-testid="history-prepare-all" size="lg" variant="outline" disabled={prepare.isPending} onClick={() => prepare.mutate('all')}>{prepare.isPending ? 'Đang đếm…' : 'Xử lý tất cả theo bộ lọc'}</Button></>:null}
  </div>
  {rows.hasNextPage && <Button data-testid="history-more" size="lg" variant="outline" disabled={rows.isFetchingNextPage} onClick={() => void rows.fetchNextPage()}>{rows.isFetchingNextPage ? 'Đang tải…' : 'Xem thêm lịch sử'}</Button>}
  {batch && <Dialog open onOpenChange={v => { if (!v && !commit.isPending) {
        setBatch(null);
        replayId.current = null;
    } }}><DialogContent data-testid="history-bulk-confirm" className="max-h-[90dvh] overflow-y-auto overscroll-contain"><DialogHeader><DialogTitle>Xử lý {batch.selected_count} lần nhắc?</DialogTitle><DialogDescription>{batch.filter.selected_refs ? 'Các lần nhắc bạn đã chọn.' : 'Toàn bộ lần nhắc chưa xử lý theo bộ lọc này, kể cả phần chưa tải.'} Lần nhắc mới sau khi đếm sẽ không được thêm vào.</DialogDescription></DialogHeader><p className="break-words text-sm">Nguồn: {sources.find(x => x[0] === source)?.[1]} · Trạng thái gửi: {status === 'all' ? 'Tất cả' : historyStatus[status]} · {from || 'Không giới hạn đầu'} – {to || 'Không giới hạn cuối'}</p><p className="text-sm">Chốt lúc {new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', dateStyle: 'short', timeStyle: 'medium' }).format(new Date(batch.cutoff))}. Xác nhận trong 15 phút.</p>{message && <p role="alert" className="text-sm break-words">{message}</p>}<Button data-testid="history-bulk-commit" size="lg" disabled={commit.isPending || batch.selected_count === 0} onClick={() => commit.mutate()}>{commit.isPending ? 'Đang xác nhận…' : 'Xác nhận xử lý ' + batch.selected_count}</Button><Button size="lg" variant="outline" disabled={commit.isPending} onClick={() => { setBatch(null); replayId.current = null; }}>Huỷ</Button></DialogContent></Dialog>}
  {opened && <ReminderSourceDialog kind={opened.source_kind as ReminderSource} sourceId={opened.source_ref.id} onClose={() => setOpened(null)}/>}
 </section>;
}
