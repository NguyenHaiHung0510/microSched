import type { MimiEvent, MimiToolActivityView } from '@/mimi-api'

const labels: Record<string, string> = {
  lifecycle: 'Vòng đời', status: 'Trạng thái', priority: 'Ưu tiên', due_from: 'Từ ngày',
  due_through: 'Đến ngày', title_contains: 'Tiêu đề chứa', updated_desc: 'Cập nhật mới nhất',
  active: 'Đang dùng', deleted: 'Đã xóa', all: 'Tất cả', open: 'Đang mở', completed: 'Đã xong',
  id: 'Định danh', title: 'Tiêu đề', due_on: 'Ngày hạn', due_at: 'Giờ hạn',
  due_precision: 'Kiểu hạn', pinned: 'Ghim', completed_at: 'Mốc hoàn thành', deleted_at: 'Mốc xóa',
}
const label = (value: string) => labels[value] ?? value

export function MimiToolActivity({ events, runId }: { events: MimiEvent[]; runId: string | null | undefined }) {
  const unique = new Map(events.filter(e => e.run_id === runId && e.kind === 'tool.read_result').map(e => [e.sequence, e]))
  if (!unique.size) return null
  return <div className="mt-2 space-y-1" data-testid="mimi-tool-activity">{[...unique.values()].sort((a, b) => a.sequence - b.sequence).map(event => {
    const activity = event.payload.activity as MimiToolActivityView | undefined
    const query = activity?.query
    return <details key={event.sequence} className="rounded-lg bg-muted/50 text-xs"><summary className="cursor-pointer p-2 font-medium">{activity?.label ?? 'Công cụ Task'} · {activity?.state === 'error' ? 'Chưa đọc được dữ liệu' : activity?.state === 'unavailable' || !activity ? 'Metadata chưa khả dụng' : 'Đã ghi nhận'}{query?.count != null ? ` · ${query.count} kết quả` : ''}</summary><div className="space-y-1 break-words px-3 pb-3">{query ? <><p>Kết quả: {query.error ? 'Lỗi truy vấn · chưa xác định số khớp' : query.count == null ? 'Chưa xác định số khớp' : `${query.count} mục trong trang`} · {query.coverage === 'complete' ? 'đủ phạm vi truy vấn' : query.coverage === 'partial' ? 'còn trang khác' : 'coverage chưa khả dụng'}</p>{query.error ? <p role="status">{query.error === 'invalid_task_query_cursor' ? 'Cursor không hợp lệ; chưa đọc dữ liệu.' : 'Công cụ báo lỗi.'}</p> : null}{query.as_of ? <p>Dữ liệu lúc {new Date(query.as_of).toLocaleString('vi-VN')}</p> : null}<p>Bộ lọc: {Object.entries(query.filter).filter(([, value]) => value != null).map(([key, value]) => `${label(key)}: ${label(value!)}`).join(' · ') || 'Không đặt'}</p><p>Sắp xếp: {label(query.sort)} · giới hạn {query.limit}</p><p>Trường yêu cầu: {query.projection.map(label).join(', ')}</p><p>Cursor yêu cầu: {query.cursor_present ? 'có' : 'không'} · trang tiếp: {query.has_next_page ? 'có' : 'không'}</p><p className="text-muted-foreground">source_version / collection_version là provenance của nguồn, tách khỏi các trường yêu cầu.</p></> : <p>Receipt đã ghi nhận; metadata chi tiết chưa khả dụng.</p>}</div></details>
  })}</div>
}
