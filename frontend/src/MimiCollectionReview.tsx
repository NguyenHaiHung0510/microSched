import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { fetchMimiSelection, type MimiChangeSet, type MimiCollectionPlan } from '@/mimi-api'
import { collectionConfirmable, collectionConfirmationNotice, collectionCounts } from '@/mimi-collection'
import { usePreviewExpired } from '@/mimi-preview-expiry'
import { mimiVietnamTimestamp } from '@/mimi-presentation'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'
import { MimiCollectionFrame, MimiCollectionTable } from '@/MimiCollectionView'

export function MimiCollectionReview({ changeSet, plan, conversationId, pending, error, onDecision, onRevise }: { changeSet: MimiChangeSet; plan: MimiCollectionPlan; conversationId: string; pending: boolean; error: string | null; onDecision: (choice: 'confirm' | 'reject') => void; onRevise: () => void }) {
  const [open, setOpen] = useState(false)
  const reviseAfterClose = useRef(false)
  const [mode, setMode] = useState<'drawer' | 'inspector'>('drawer')
  const [tableState, setTableState] = useState({ query: '', classification: 'all', page: 0, expanded: null as string | null })
  const expired = usePreviewExpired(changeSet.expires_at)
  const selection = useQuery({ queryKey: ['mimi', 'selection', conversationId, plan.selection_id], queryFn: () => fetchMimiSelection(conversationId, plan.selection_id!), enabled: !!plan.selection_id, ...NO_POLLING_QUERY_OPTIONS })
  const counts = collectionCounts(plan, selection.data)
  const selectionReady = collectionConfirmable(plan, selection.data)
  const confirmationNotice = collectionConfirmationNotice(changeSet)
  const disabled = pending || expired || changeSet.state !== 'pending' || !selectionReady || confirmationNotice !== null
  const review = <div className="space-y-3 min-w-0" data-testid="mimi-collection-review">
    <p className="rounded-lg bg-muted p-3 text-sm" data-testid="mimi-global-counts">Toàn bộ tập đã chốt: {counts.included} bao gồm · {counts.excluded} loại trừ · {counts.uncertain} chưa chắc · <strong>{counts.affected} Task sẽ thay đổi</strong>.</p>
    <p className="text-xs text-muted-foreground">Tìm kiếm và phân trang chỉ đổi phần đang xem. Xác nhận luôn áp dụng cả {plan.entries.length} Task đã chốt, cùng một giao dịch.</p>
    {selection.data?.explicitly_named_subset ? <p className="text-xs text-warn">Đây là tập được nêu đích danh. Nguồn chưa hoàn tất hoặc các mục ngoài tập này vẫn chưa được kết luận; xác nhận chỉ tác động đúng {plan.entries.length} ID đã chốt.</p> : null}
    {selection.data ? <details className="rounded-lg border p-3"><summary className="cursor-pointer text-sm font-semibold">Nguồn và lý do chọn / loại trừ</summary><p className="mt-2 text-sm">{selection.data.intent}</p><p className="text-xs">Biến thể: {selection.data.variants_considered.join(', ')} · nguồn lúc {mimiVietnamTimestamp(selection.data.as_of)}</p><ul className="mt-2 max-h-56 overflow-auto text-xs">{selection.data.members.map((m) => <li key={m.id} className="break-words border-t py-2">{m.classification} · {m.id} · v{m.collection_version} · {m.reason}</li>)}</ul></details> : null}
    {selection.isPending && plan.selection_id ? <p role="status">Đang tải tập nguồn đã chốt…</p> : null}
    {selection.isError ? <div role="alert"><p>Chưa đọc được tập nguồn. Chưa thể xác nhận.</p><Button variant="outline" onClick={() => void selection.refetch()}>Đọc lại nguồn</Button></div> : null}
    <MimiCollectionTable plan={plan} selection={selection.data} state={tableState} onStateChange={setTableState} />
    <p className="text-xs">{expired ? 'Preview đã hết hạn. Cần phương án mới.' : `Hết hạn ${mimiVietnamTimestamp(changeSet.expires_at)}. Chưa ghi thay đổi.`}</p>
    {confirmationNotice ? <p role="status" className="text-sm" data-testid="mimi-confirmation-preflight">{confirmationNotice}</p> : null}
    {error ? <p role="alert" className="text-sm text-bad">{error}</p> : null}
    <div className="flex flex-wrap gap-2" data-testid="mimi-preview-actions"><Button variant="secondary" disabled={pending || expired} onClick={() => { if (open) { reviseAfterClose.current = true; setOpen(false) } else onRevise() }}>Sửa phương án này</Button><Button disabled={disabled} onClick={() => onDecision('confirm')}><Check />Xác nhận toàn bộ {plan.entries.length} Task</Button><Button variant="outline" disabled={pending || expired} onClick={() => onDecision('reject')}><X />Từ chối</Button></div>
    <details className="text-xs"><summary className="cursor-pointer">Mã đối chiếu</summary><p className="break-all">{changeSet.id} · {changeSet.digest}</p></details>
  </div>
  return <MimiCollectionFrame title={`${expired ? 'Preview hết hạn' : plan.undo_receipt_id ? 'Preview hoàn tác' : 'Chờ bạn duyệt'} · ${plan.entries.length} Task`} actions={<><Button size="sm" variant="outline" onClick={() => { setMode('drawer'); setOpen(true) }}>Xem và duyệt</Button><Button size="sm" variant="ghost" aria-pressed={mode === 'inspector'} onClick={() => setMode(mode === 'inspector' ? 'drawer' : 'inspector')}>Inspector B</Button></>}>
    {mode === 'inspector' ? <div className="mt-3 max-h-[50dvh] overflow-auto">{review}</div> : null}
    <Dialog open={open} onOpenChange={setOpen}><DialogContent onCloseAutoFocus={event => { if (reviseAfterClose.current) { event.preventDefault(); reviseAfterClose.current = false; onRevise() } }} className="max-h-[90dvh] w-[calc(100%-1rem)] max-w-5xl sm:max-w-5xl overflow-y-auto"><DialogHeader><DialogTitle>Duyệt toàn bộ {plan.entries.length} Task</DialogTitle><DialogDescription>Đối chiếu nội dung, checklist và reminder trước khi xác nhận.</DialogDescription></DialogHeader>{review}</DialogContent></Dialog>
  </MimiCollectionFrame>
}
