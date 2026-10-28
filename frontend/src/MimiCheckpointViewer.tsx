import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchMimiCheckpoint, type MimiCheckpointView, type MimiCheckpointConstraint } from './mimi-api'
import { MimiMessageText } from './MimiMessageText'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'

function Constraints({ items }: { items: MimiCheckpointConstraint[] }) {
  return <ul className="mt-2 space-y-3">
    {items.map((item) => <li key={item.id} className="min-w-0">
      <MimiMessageText text={item.text} />
      <p className="text-xs text-muted-foreground">
        {item.status === 'active' ? 'Đang áp dụng' : item.status === 'superseded' ? 'Đã thay thế' : 'Đã giải quyết'}
        {item.source?.sequence ? ` · Tin nhắn ${item.source.sequence}` : ' · Nguồn từ checkpoint trước'}
      </p>
      {item.source?.quote ? <blockquote className="mt-1 border-l-2 pl-3 text-xs whitespace-pre-wrap break-words">{item.source.quote}</blockquote> : null}
    </li>)}
  </ul>
}

export function MimiCheckpointContents({ view }: { view: MimiCheckpointView }) {
  const checkpoint = view.checkpoint
  if (!checkpoint) return <p className="mt-2 text-sm">Chưa có bản tóm tắt được kích hoạt. Lịch sử hội thoại vẫn là nguồn ngữ cảnh.</p>
  const active = checkpoint.constraint_ledger?.filter((item) => item.status === 'active') ?? []
  const historical = checkpoint.constraint_ledger?.filter((item) => item.status !== 'active') ?? []
  return <div className="mt-3 min-w-0 space-y-3" data-testid="mimi-checkpoint-content">
    <p className="text-xs text-muted-foreground">Bản tóm tắt đến tin nhắn {view.frontier}; các tin nhắn sau đó được bổ sung riêng. Đây là thông tin ghi nhớ, không cấp quyền thực thi hoặc thay preview đang chờ duyệt.</p>
    {view.activated_at ? <p className="text-xs text-muted-foreground">Được kích hoạt lúc {new Date(view.activated_at).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })} (GMT+7). Đây là thời điểm tạo bản ghi nhớ, không phải lúc đồng bộ toàn bộ dữ liệu hiện tại.</p> : null}
    <p className="text-xs font-semibold">{checkpoint.summary_kind === 'semantic_model' ? 'Tóm tắt bằng model' : 'Trích đoạn lịch sử'}</p>
    <MimiMessageText text={checkpoint.summary} />
    {active.length ? <section aria-label="Ràng buộc đang áp dụng"><h3 className="text-sm font-semibold">Ràng buộc đang áp dụng</h3><Constraints items={active} /></section> : null}
    {!checkpoint.constraint_ledger && (checkpoint.decisions.length || checkpoint.unresolved.length) ? <section aria-label="Ghi nhận trong checkpoint"><h3 className="text-sm font-semibold">Ghi nhận trong checkpoint</h3><ul className="mt-2 list-disc pl-5 text-sm">{[...checkpoint.decisions, ...checkpoint.unresolved].map((text, index) => <li key={index}>{text}</li>)}</ul></section> : null}
    {historical.length ? <details><summary className="cursor-pointer text-sm">Ràng buộc đã thay thế hoặc giải quyết ({historical.length})</summary><Constraints items={historical} /></details> : null}
    <details className="min-w-0"><summary className="cursor-pointer text-xs">Nguồn và mã kiểm chứng ({checkpoint.source_refs.length})</summary>
      <p className="mt-2 break-all text-xs">Checkpoint: {view.checkpoint_id} · SHA-256 của checkpoint đầy đủ đã kiểm chứng: {view.checkpoint_sha256}</p>
      <ul className="mt-2 space-y-1 text-xs">{checkpoint.source_refs.map((ref) => <li className="break-all" key={ref.id}>Tin nhắn {ref.sequence} · {ref.id} · {ref.sha256}</li>)}</ul>
    </details>
  </div>
}

export function MimiCheckpointViewer({ conversationId, frontier, generation }: { conversationId: string; frontier: number; generation: number }) {
  const [open, setOpen] = useState(false)
  const query = useQuery({
    queryKey: ['mimi-checkpoint', conversationId, frontier, generation],
    queryFn: () => fetchMimiCheckpoint(conversationId),
    enabled: open,
    retry: false,
    ...NO_POLLING_QUERY_OPTIONS,
  })
  return <details className="mt-3 min-w-0" data-testid="mimi-checkpoint-viewer" onToggle={(event) => {
    const nextOpen = event.currentTarget.open
    setOpen(nextOpen)
  }}>
    <summary className="cursor-pointer text-sm font-semibold">Xem bản tóm tắt hiện hành</summary>
    {open && (query.isFetching || query.isPending) ? <p role="status" className="mt-2 text-sm">Đang kiểm tra bản tóm tắt…</p>
      : open && (query.isError || (query.data && query.data.conversation_id !== conversationId)) ? <p role="alert" className="mt-2 text-sm">Không thể kiểm chứng bản tóm tắt hiện hành. Không dùng bản lưu cũ; hãy đóng và mở lại để thử đọc.</p>
      : open && query.data ? <MimiCheckpointContents view={query.data} /> : null}
  </details>
}
