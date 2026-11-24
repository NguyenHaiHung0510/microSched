import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ApiError } from '@/api'
import { Button } from '@/components/ui/button'
import { fetchMimiReceiptDiff } from '@/mimi-api'
import { MimiCollectionFrame, MimiCollectionTable } from '@/MimiCollectionView'
import { mimiVietnamTimestamp } from '@/mimi-presentation'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'

function unavailableMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 403) return 'Chi tiết biên nhận không được phép hiển thị trong phạm vi hiện tại.'
    if (error.status === 404 || error.status === 410) return 'Biên nhận cũ hoặc chi tiết trước/sau không còn đọc được.'
    if (error.status === 409) return 'Chi tiết biên nhận không còn hợp lệ để hiển thị. Hãy đọc lại trạng thái.'
  }
  return 'Chưa đọc được chi tiết trước/sau của biên nhận này.'
}

export function MimiAppliedReceipt({ conversationId, messageId, receiptId, undoPending, undoDisabled, undoError, onUndo, onOpenTasks }: {
  conversationId: string; messageId: string; receiptId: string; undoPending: boolean; undoDisabled: boolean
  undoError: string | null; onUndo: (receiptId: string) => void; onOpenTasks: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const query = useQuery({
    queryKey: ['mimi', 'receipt-diff', conversationId, messageId, receiptId],
    queryFn: ({ signal }) => fetchMimiReceiptDiff(receiptId, signal),
    enabled: expanded, retry: false, gcTime: 0,
    ...NO_POLLING_QUERY_OPTIONS,
  })
  // A refetch failure or an identity change must never reveal an older projection.
  const diff = query.isSuccess && !query.isFetching && query.data?.receipt_id === receiptId ? query.data : null
  return <MimiCollectionFrame title={diff ? `Đã áp dụng thay đổi · ${diff.plan.entries.length} Task` : 'Đã áp dụng thay đổi'} testId="mimi-applied-receipt" actions={<Button size="sm" variant="outline" onClick={onOpenTasks}>Mở Task</Button>}>
    <details className="mt-3" onToggle={event => { if (event.target === event.currentTarget) setExpanded(event.currentTarget.open) }}>
      <summary className="cursor-pointer text-sm font-semibold">Xem thay đổi</summary>
      <div className="mt-3 space-y-3" data-receipt-id={receiptId}>
        {query.isPending || query.isFetching ? <p role="status" className="text-sm">Đang đọc thay đổi đã lưu…</p> : diff ? <>
          <p className="rounded-lg bg-muted p-3 text-sm">{diff.plan.entries.length} Task đã thay đổi · <time dateTime={diff.executed_at}>{mimiVietnamTimestamp(diff.executed_at)}</time>. Chỉ đọc; đây là nội dung tại lúc áp dụng.</p>
          <MimiCollectionTable key={receiptId} plan={diff.plan} executed />
          {diff.undo_available ? <Button variant="outline" disabled={undoPending || undoDisabled} onClick={() => onUndo(receiptId)}>Chuẩn bị hoàn tác</Button> : <p className="text-xs text-muted-foreground">Biên nhận này hiện không có hoàn tác.</p>}
          <p className="text-xs text-muted-foreground">Hoàn tác tạo preview mới có kiểm tra phiên bản; cần xác nhận riêng.</p>
          {undoError ? <p role="alert" className="text-sm text-bad">{undoError}</p> : null}
        </> : <div role="alert" className="space-y-2 text-sm">
          <p>{query.isError ? unavailableMessage(query.error) : 'Biên nhận này không có chi tiết trước/sau để hiển thị.'} Thông báo đã áp dụng vẫn được giữ; không suy ra nội dung từ preview hoặc biên nhận khác.</p>
          <Button variant="outline" onClick={() => void query.refetch()}>Đọc lại chi tiết</Button>
        </div>}
        <details className="text-xs"><summary className="cursor-pointer">Mã đối chiếu</summary><p className="break-all">Receipt {receiptId}</p></details>
      </div>
    </details>
  </MimiCollectionFrame>
}
