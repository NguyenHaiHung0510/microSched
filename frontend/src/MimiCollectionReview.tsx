import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronLeft, ChevronRight, Check, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { fetchMimiSelection, type MimiChangeSet, type MimiCollectionEntry, type MimiCollectionPlan } from '@/mimi-api'
import { collectionConfirmable, collectionConfirmationNotice, collectionCounts, collectionFieldDiff, collectionPage } from '@/mimi-collection'
import { usePreviewExpired } from '@/mimi-preview-expiry'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'
import { MimiCollectionEntryDetails } from '@/MimiCollectionEntryDetails'
import { checklistSummary, collectionActionLabel, reminderEffectLabel, reviewFieldLabel } from '@/mimi-review-readable'

export function MimiCollectionReview({ changeSet, plan, conversationId, pending, error, onDecision, onRevise }: { changeSet: MimiChangeSet; plan: MimiCollectionPlan; conversationId: string; pending: boolean; error: string | null; onDecision: (choice: 'confirm' | 'reject') => void; onRevise: () => void }) {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<'drawer' | 'inspector'>('drawer')
  const [query, setQuery] = useState('')
  const [classification, setClassification] = useState('all')
  const [page, setPage] = useState(0)
  const [expanded, setExpanded] = useState<string | null>(null)
  const expired = usePreviewExpired(changeSet.expires_at)
  const selection = useQuery({ queryKey: ['mimi', 'selection', conversationId, plan.selection_id], queryFn: () => fetchMimiSelection(conversationId, plan.selection_id!), enabled: !!plan.selection_id, ...NO_POLLING_QUERY_OPTIONS })
  const counts = collectionCounts(plan, selection.data)
  const view = collectionPage(plan, query, classification, selection.data, page)
  const selectionReady = collectionConfirmable(plan, selection.data)
  const confirmationNotice = collectionConfirmationNotice(changeSet)
  const disabled = pending || expired || changeSet.state !== 'pending' || !selectionReady || confirmationNotice !== null
  const review = <div className="space-y-3 min-w-0" data-testid="mimi-collection-review">
    <p className="rounded-lg bg-muted p-3 text-sm" data-testid="mimi-global-counts">Toàn bộ tập đã chốt: {counts.included} bao gồm · {counts.excluded} loại trừ · {counts.uncertain} chưa chắc · <strong>{counts.affected} Task sẽ thay đổi</strong>.</p>
    <p className="text-xs text-muted-foreground">Tìm kiếm và phân trang chỉ đổi phần đang xem. Xác nhận luôn áp dụng cả {plan.entries.length} Task đã chốt, cùng một giao dịch.</p>
    {selection.data?.explicitly_named_subset ? <p className="text-xs text-warn">Đây là tập được nêu đích danh. Nguồn chưa hoàn tất hoặc các mục ngoài tập này vẫn chưa được kết luận; xác nhận chỉ tác động đúng {plan.entries.length} ID đã chốt.</p> : null}
    {selection.data ? <details className="rounded-lg border p-3"><summary className="cursor-pointer text-sm font-semibold">Nguồn và lý do chọn / loại trừ</summary><p className="mt-2 text-sm">{selection.data.intent}</p><p className="text-xs">Biến thể: {selection.data.variants_considered.join(', ')} · nguồn lúc {new Date(selection.data.as_of).toLocaleString('vi-VN')}</p><ul className="mt-2 max-h-56 overflow-auto text-xs">{selection.data.members.map((m) => <li key={m.id} className="break-words border-t py-2">{m.classification} · {m.id} · v{m.collection_version} · {m.reason}</li>)}</ul></details> : null}
    {selection.isPending && plan.selection_id ? <p role="status">Đang tải tập nguồn đã chốt…</p> : null}
    {selection.isError ? <div role="alert"><p>Chưa đọc được tập nguồn. Chưa thể xác nhận.</p><Button variant="outline" onClick={() => void selection.refetch()}>Đọc lại nguồn</Button></div> : null}
    <div className="flex flex-wrap items-center gap-2"><Input className="min-w-0 flex-1 text-base md:text-sm" aria-label="Tìm trong preview" placeholder="Tìm tiêu đề hoặc ID…" value={query} onChange={(e) => { setQuery(e.target.value); setPage(0) }} /><Select value={classification} onValueChange={(value) => { setClassification(value); setPage(0) }}><SelectTrigger aria-label="Lọc phân loại" className="w-40"><SelectValue /></SelectTrigger><SelectContent>{[['all','Tất cả'],['included','Bao gồm'],['excluded','Loại trừ'],['uncertain','Chưa chắc']].map(([value,label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></Select></div>
    <div className="overflow-x-auto rounded-lg border"><table className="w-full text-left text-xs"><caption className="sr-only">Thay đổi Task đã chốt, tối đa 20 dòng mỗi trang</caption><thead className="bg-muted"><tr><th className="p-2">Task / thao tác</th><th className="p-2">Tóm tắt</th><th className="p-2">Chi tiết</th></tr></thead><tbody>{view.entries.map((entry) => <Row key={entry.id} entry={entry} expanded={expanded === entry.id} onToggle={() => setExpanded(expanded === entry.id ? null : entry.id)} />)}</tbody></table></div>
    {!view.visibleCount ? <p className="text-sm text-muted-foreground">Không có dòng khớp bộ lọc; phạm vi xác nhận vẫn là {plan.entries.length} Task.</p> : null}
    <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-xs">Trang {view.currentPage + 1}/{view.pageCount} · {view.visibleCount}/{plan.entries.length} dòng khớp</span><div className="flex gap-1"><Button size="icon" variant="outline" aria-label="Trang trước" disabled={view.currentPage === 0} onClick={() => setPage(view.currentPage - 1)}><ChevronLeft /></Button><Button size="icon" variant="outline" aria-label="Trang sau" disabled={view.currentPage + 1 >= view.pageCount} onClick={() => setPage(view.currentPage + 1)}><ChevronRight /></Button></div></div>
    <p className="text-xs">{expired ? 'Preview đã hết hạn. Cần phương án mới.' : `Hết hạn ${new Date(changeSet.expires_at).toLocaleString('vi-VN')}. Chưa ghi thay đổi.`}</p>
    {confirmationNotice ? <p role="status" className="text-sm" data-testid="mimi-confirmation-preflight">{confirmationNotice}</p> : null}
    {error ? <p role="alert" className="text-sm text-bad">{error}</p> : null}
    <div className="flex flex-wrap gap-2" data-testid="mimi-preview-actions"><Button variant="secondary" disabled={pending || expired} onClick={onRevise}>Sửa phương án này</Button><Button disabled={disabled} onClick={() => onDecision('confirm')}><Check />Xác nhận toàn bộ {plan.entries.length} Task</Button><Button variant="outline" disabled={pending || expired} onClick={() => onDecision('reject')}><X />Từ chối</Button></div>
    <details className="text-xs"><summary className="cursor-pointer">Mã đối chiếu</summary><p className="break-all">{changeSet.id} · {changeSet.digest}</p></details>
  </div>
  return <section className="shrink-0 rounded-xl border bg-card p-3" data-testid="mimi-change-set"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-semibold">{expired ? 'Preview hết hạn' : plan.undo_receipt_id ? 'Preview hoàn tác' : 'Chờ bạn duyệt'} · {plan.entries.length} Task</p><div className="flex gap-1"><Button size="sm" variant="outline" onClick={() => { setMode('drawer'); setOpen(true) }}>Xem và duyệt</Button><Button size="sm" variant="ghost" aria-pressed={mode === 'inspector'} onClick={() => setMode(mode === 'inspector' ? 'drawer' : 'inspector')}>Inspector B</Button></div></div>{mode === 'inspector' ? <div className="mt-3 max-h-[50dvh] overflow-auto">{review}</div> : null}<Dialog open={open} onOpenChange={setOpen}><DialogContent className="max-h-[90dvh] w-[calc(100%-1rem)] max-w-5xl sm:max-w-5xl overflow-y-auto"><DialogHeader><DialogTitle>Duyệt toàn bộ {plan.entries.length} Task</DialogTitle><DialogDescription>Đối chiếu nội dung, checklist và reminder trước khi xác nhận.</DialogDescription></DialogHeader>{review}</DialogContent></Dialog></section>
}
function Row({ entry, expanded, onToggle }: { entry: MimiCollectionEntry; expanded: boolean; onToggle: () => void }) {
  return <><tr className="border-t align-top" data-testid="mimi-review-row"><td className="max-w-64 p-2"><p className="break-words font-semibold">{String(entry.after.fields.title ?? entry.before?.fields.title ?? 'Task')}</p><p className="text-muted-foreground">{collectionActionLabel(entry.command.action)}</p></td><td className="p-2"><p>{collectionFieldDiff(entry).length ? collectionFieldDiff(entry).map((field) => reviewFieldLabel(field.key)).join(', ') : 'Các trường Task giữ nguyên'}</p><p className="text-muted-foreground">{checklistSummary(entry)}</p><p className="text-muted-foreground">{reminderEffectLabel(entry)}</p></td><td className="p-2"><Button size="sm" variant="ghost" aria-expanded={expanded} onClick={onToggle}><ChevronDown className="size-4" />{expanded ? 'Thu gọn' : 'Xem đủ'}</Button></td></tr>{expanded ? <tr className="border-t"><td colSpan={3}><MimiCollectionEntryDetails entry={entry} /></td></tr> : null}</>
}
