import { useState } from 'react'
import type { QueryKey } from '@tanstack/react-query'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError } from '@/api'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { adapterFor, hasLivePrivateSession, requiresPrivateRow } from '@/lib/outbox-adapters'
import { canDiscardOutboxRow, discardOutboxTree } from '@/lib/outbox-db'
import { useDomainOutbox } from '@/lib/use-domain-outbox'

function operationLabel(kind: string, privateHidden: boolean) {
  if (privateHidden) return 'Thay đổi riêng tư'
  if (kind.startsWith('task_item.')) return 'Checklist task'
  if (kind.startsWith('task.')) return 'Task'
  if (kind.startsWith('note_item.')) return 'Checklist ghi chú'
  if (kind.startsWith('note.')) return 'Ghi chú'
  if (kind.startsWith('calendar_') || kind.startsWith('day_annotation.')) return 'Lịch'
  if (kind.startsWith('tracker_group.')) return 'Nhóm tracker'
  if (kind.startsWith('tracker.')) return 'Tracker'
  if (kind.startsWith('entry.')) return 'Bản ghi tracker'
  if (kind.startsWith('subscription.')) return 'Đăng ký'
  if (kind.startsWith('setting.')) return 'Cài đặt'
  if (kind === 'reminder.confirm') return 'Lời nhắc'
  return 'Thay đổi chưa nhận diện'
}

function stateReason(state: string, errorCode: string | null, privateHidden: boolean) {
  if (privateHidden) return 'Nội dung đang được ẩn cho tới khi mở khoá riêng tư.'
  if (state === 'pending') return 'Chờ có kết nối để gửi.'
  if (state === 'outcome_unknown') return 'Đang xác minh lần gửi trước với máy chủ.'
  if (state === 'auth_hold') return 'Cần đăng nhập lại; hàng đợi sẽ tiếp tục sau khi đăng nhập.'
  if (state === 'private_hold') return 'Cần mở khoá riêng tư để tiếp tục gửi.'
  if (state === 'suppressed') return 'Đang chờ thay đổi cha được xử lý.'
  const reasons: Record<string, string> = {
    HTTP_400: 'Máy chủ từ chối dữ liệu không hợp lệ.',
    HTTP_404: 'Không tìm thấy đối tượng để áp dụng thay đổi.',
    HTTP_409: 'Dữ liệu xung đột với trạng thái hiện tại.',
    HTTP_422: 'Dữ liệu không vượt qua kiểm tra nghiệp vụ.',
    INVALID_COMMAND: 'Lệnh không còn phù hợp với hợp đồng hiện tại.',
    UNKNOWN_OPERATION: 'Phiên bản ứng dụng không nhận diện lệnh này.',
  }
  return reasons[errorCode ?? ''] ?? 'Máy chủ không nhận thay đổi này.'
}

export function OutboxStatus({ queryKey = [], privateUnlocked = false }: { queryKey?: QueryKey; privateUnlocked?: boolean }) {
  const client = useQueryClient()
  const global = queryKey.length === 0
  const state = useDomainOutbox(queryKey, privateUnlocked, global)
  const [open, setOpen] = useState(false)
  const [discarding, setDiscarding] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  async function discardTree(operationId: number) {
    setDiscarding(operationId)
    setActionError(null)
    try {
      const discarded = await discardOutboxTree(operationId)
      for (const row of discarded) {
        try {
          await adapterFor(row.operation_kind).discardOrRollback(client, row)
        } catch {
          // Unknown operations fail closed; do not guess which cache to change.
        }
      }
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : 'Không thể xoá thay đổi khỏi hàng đợi trên thiết bị này.')
    } finally {
      setDiscarding(null)
    }
  }

  if (!state.rows.length && !state.webLocksUnavailable && !state.unavailable && !state.readError) return null

  const queued = state.rows.filter((row) => row.state !== 'failed' && row.state !== 'suppressed').length
  const failed = state.rows.length - queued
  return (
    <>
      {state.unavailable ? <p className="text-sm text-muted-foreground" role="status">
        Lưu ngoại tuyến chưa khả dụng trên thiết bị này.{state.rows.length ? ' Các thay đổi đang chờ vẫn được giữ; bạn có thể xem hàng đợi bên dưới.' : ''}
      </p> : null}
      {state.readError ? <p className="text-sm text-bad" role="status">Chưa đọc được trạng thái hàng đợi.</p> : null}
      {state.webLocksUnavailable ? <p data-testid="outbox-lock-warning" className="text-sm text-muted-foreground" role="status">
        Trình duyệt này chưa hỗ trợ khoá gửi an toàn giữa các thẻ hoặc đang ở ngữ cảnh không bảo mật. Thay đổi vẫn được lưu trên thiết bị; gửi sẽ tiếp tục khi dùng ngữ cảnh hỗ trợ.
      </p> : null}
      {!state.readError && state.rows.length > 0 ? <Button data-testid="outbox-indicator" variant="outline" size="lg" className="min-h-11" aria-haspopup="dialog" onClick={() => setOpen(true)}>
        {queued > 0 ? queued + ' đang chờ gửi' : failed + ' cần xử lý'}{failed > 0 ? ' · ' + failed + ' lỗi' : ''}
      </Button> : null}
      {!state.readError && state.rows.length > 0 ? <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="outbox-panel" className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
          <DialogHeader className="pr-12">
            <DialogTitle>Hàng đợi ngoại tuyến</DialogTitle>
            <DialogDescription>Các thay đổi được lưu trên thiết bị. Mục đang chờ sẽ tự tiếp tục khi có mạng hoặc quyền cần thiết.</DialogDescription>
          </DialogHeader>
          {actionError ? <p className="text-sm text-bad" role="alert">{actionError}</p> : null}
          <div className="space-y-3">
            {state.rows.map((row) => {
              const privateHidden = requiresPrivateRow(row) && !privateUnlocked
              const label = operationLabel(row.operation_kind, privateHidden)
              const reason = stateReason(row.state, row.last_error_code, privateHidden)
              return (
                <article data-testid="outbox-item" key={row.operation_id} className="space-y-2 rounded-lg border border-border bg-card p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="font-bold">{label}</h3>
                    <Badge variant={row.state === 'failed' || row.state === 'suppressed' ? 'destructive' : 'secondary'}>{reason.split(/[.;]/, 1)[0]}</Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">{reason}</p>
                  <Button data-testid="outbox-item-discard" variant="ghost" size="lg" className="min-h-11 text-bad hover:text-bad" disabled={discarding === row.operation_id || !canDiscardOutboxRow(row)} onClick={() => void discardTree(row.operation_id!)}>
                    {discarding === row.operation_id ? 'Đang xoá…' : canDiscardOutboxRow(row) ? 'Xoá bỏ thay đổi' : 'Chờ xác minh hoặc gửi tiếp'}
                  </Button>
                </article>
              )
            })}
          </div>
        </DialogContent>
      </Dialog> : null}
    </>
  )
}

export function OutboxEntityStatus({
  entityId,
}: {
  entityId: string
}) {
  const client = useQueryClient()
  useQuery({ queryKey: ['session'], enabled: false })
  const privateUnlocked = hasLivePrivateSession(client)
  const state = useDomainOutbox([], privateUnlocked, true)
  const rows = state.rows.filter((row) =>
    (row.state === 'failed' || row.state === 'suppressed') &&
    (row.entity_id === entityId || row.parent_id === entityId))
  if (state.readError || rows.length === 0) return null
  const row = rows[rows.length - 1]
  const privateHidden = requiresPrivateRow(row) && !privateUnlocked
  const reason = stateReason(row.state, row.last_error_code, privateHidden)
  return (
    <Badge
      data-testid="outbox-entity-state"
      variant='destructive'
      role="status"
      aria-live="polite"
    >
      Chưa gửi được
      <span className="sr-only">{reason}</span>
    </Badge>
  )
}
