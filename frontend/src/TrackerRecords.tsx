import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronUp, Pencil, Trash2 } from 'lucide-react'
import { apiRequest } from '@/api'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { standardRefetchInterval } from '@/query-polling'
import { formatQuantity, formatVnd, trackerQueryKey, type Entry, type Tracker } from '@/tracker-ui'
import { recordsUrl, type RecordMode, type RecordsSelection } from '@/tracker-records'

const MODE_LABELS: Record<RecordMode, string> = { recent:'20 bản ghi gần nhất', day:'Theo ngày', month:'Theo tháng', quarter:'Theo quý', year:'Theo năm' }
export function TrackerRecords({ trackers, selection, onChange, onEdit, onRemove, showListPrice, privateUnlocked }: {
  trackers: Tracker[]; selection: RecordsSelection; onChange: (value: RecordsSelection) => void
  onEdit: (entry: Entry) => void; onRemove: (entry: Entry) => void; showListPrice: boolean; privateUnlocked: boolean
}) {
  const url = recordsUrl(selection)
  const query = useQuery({
    queryKey: [...trackerQueryKey('entries'), 'explorer', privateUnlocked, url],
    queryFn: ({ signal }) => apiRequest<{ items: Entry[] }>(url!, { signal }),
    enabled: url !== null,
    refetchInterval: standardRefetchInterval,
  })
  const change = (patch: Partial<RecordsSelection>) => onChange({ ...selection, ...patch, page:0 })
  const items = query.data?.items.slice(0, selection.mode === 'recent' ? 20 : 50) ?? []
  const next = selection.mode !== 'recent' && (query.data?.items.length ?? 0) > 50
  const dateType = selection.mode === 'day' ? 'date' : selection.mode === 'year' ? 'number' : 'month'
  const dateValue = dateType === 'date' ? selection.anchor : dateType === 'number' ? String(Number(selection.anchor.slice(0,4))) : selection.anchor.slice(0,7)
  return <Card id="tracker-records" data-testid="tracker-records" className="scroll-mt-4 gap-3 p-4 shadow-1 ring-0">
    <Button type="button" variant="ghost" data-testid="tracker-entries-toggle" aria-expanded={selection.expanded} aria-controls="tracker-recent-entries" className="h-auto min-h-11 w-full justify-between gap-3 whitespace-normal p-0 text-left hover:bg-transparent" onClick={() => onChange({ ...selection, expanded:!selection.expanded })}>
      <h3 className="text-base font-bold">Xem chi tiết các bản ghi</h3>
      {selection.expanded ? <ChevronUp className="size-4 shrink-0" /> : <ChevronDown className="size-4 shrink-0" />}
    </Button>
    {selection.expanded ? <div id="tracker-recent-entries" className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="min-w-0 space-y-1 text-sm font-semibold"><span>Cách xem</span>
          <Select value={selection.mode} onValueChange={value => change({mode:value as RecordMode,order:value === 'recent' ? 'desc' : selection.order})}><SelectTrigger data-testid="records-mode" className="min-h-11 w-full"><SelectValue /></SelectTrigger><SelectContent>{Object.entries(MODE_LABELS).map(([value,label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></Select>
        </label>
        <label className="min-w-0 space-y-1 text-sm font-semibold"><span>Tracker</span>
          <Select value={selection.trackerId} onValueChange={trackerId => change({trackerId})}><SelectTrigger data-testid="records-tracker" className="min-h-11 w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Tất cả tracker</SelectItem>{trackers.map(t => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}</SelectContent></Select>
        </label>
        {selection.mode !== 'recent' ? <>
          <label className="min-w-0 space-y-1 text-sm font-semibold"><span>{selection.mode === 'quarter' ? 'Tháng trong quý' : selection.mode === 'year' ? 'Năm' : selection.mode === 'month' ? 'Tháng' : 'Ngày'}</span>
            <Input data-testid="records-date" className="min-h-11 w-full text-base" type={dateType} min={dateType === 'number' ? 1 : undefined} max={dateType === 'number' ? 9998 : undefined} value={dateValue} onChange={e => {
              const value = e.target.value
              const anchor = dateType === 'date' ? value : dateType === 'number' ? (/^[0-9]{1,4}$/.test(value) ? value.padStart(4,'0')+'-01-01' : '') : value+'-01'
              change({anchor})
            }} />
          </label>
          <label className="min-w-0 space-y-1 text-sm font-semibold"><span>Sắp xếp</span>
            <Select value={selection.order} onValueChange={order => change({order:order as 'asc'|'desc'})}><SelectTrigger data-testid="records-order" className="min-h-11 w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="desc">Mới nhất trước</SelectItem><SelectItem value="asc">Cũ nhất trước</SelectItem></SelectContent></Select>
          </label>
        </> : null}
      </div>
      <p className="text-xs text-muted-foreground">Ngày và kỳ theo giờ Việt Nam · {selection.mode === 'recent' ? 'Tối đa 20 bản ghi mới nhất' : `Trang ${selection.page+1} · tối đa 50 bản ghi mỗi trang`}</p>
      {!url ? <p role="alert" className="text-sm text-bad">Chọn ngày hoặc năm hợp lệ để xem bản ghi.</p> : query.isError ? <div role="alert" className="space-y-2"><p className="text-sm text-bad">Không tải được bản ghi.</p><Button variant="outline" className="min-h-11" onClick={() => void query.refetch()}>Thử lại</Button></div> : query.isPending ? <p role="status" className="text-sm text-muted-foreground">Đang tải bản ghi…</p> : <>
        <div className="divide-y divide-border" data-testid="records-list">
          {items.map(entry => {
            const tracker = trackers.find(t => t.id === entry.tracker_id)
            return <div key={entry.id} data-testid="entry-row" data-entry-id={entry.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 py-3">
              <div className="min-w-0"><p className="break-words text-sm font-semibold">{tracker?.name ?? 'Tracker'}</p><p className="text-xs text-muted-foreground">{entry.occurred_at ? new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(entry.occurred_at)) : ''}</p>{entry.note_md ? <p className="mt-1 whitespace-pre-wrap break-words text-sm text-muted-foreground">{entry.note_md}</p> : null}</div>
              <div className="flex flex-wrap items-center justify-end gap-1 sm:gap-2"><span className="basis-full text-right text-sm font-bold tabular-nums sm:basis-auto">{showListPrice && entry.list_amount != null && entry.amount != null && entry.list_amount !== entry.amount ? <span className="mr-2 text-xs font-normal text-muted-foreground line-through">{formatVnd(entry.list_amount)}</span> : null}{entry.amount != null ? formatVnd(entry.amount) : entry.quantity != null ? formatQuantity(entry.quantity) : 'Đã ghi'}</span>
                <Button data-testid="entry-edit" data-entry-id={entry.id} variant="ghost" size="icon-lg" className="size-11" aria-label="Sửa bản ghi" onClick={() => onEdit(entry)}><Pencil /></Button>
                <Button data-testid="entry-undo" data-entry-id={entry.id} variant="ghost" size="icon-lg" className="size-11" aria-label="Xoá bản ghi" onClick={() => onRemove(entry)}><Trash2 /></Button>
              </div>
            </div>
          })}
        </div>
        {!items.length ? <p className="text-sm text-muted-foreground">Không có bản ghi trong lựa chọn này.</p> : null}
        {selection.mode !== 'recent' ? <div className="flex flex-wrap items-center justify-between gap-2">
          <Button data-testid="records-prev" variant="outline" className="min-h-11" disabled={selection.page===0 || query.isFetching} onClick={() => onChange({...selection,page:selection.page-1})}>Trang trước</Button>
          <span className="text-sm">Trang {selection.page+1} · {items.length} bản ghi</span>
          <Button data-testid="records-next" variant="outline" className="min-h-11" disabled={!next || query.isFetching} onClick={() => onChange({...selection,page:selection.page+1})}>Trang sau</Button>
        </div> : null}
      </>}
    </div> : null}
  </Card>
}
