import type { MimiCollectionEntry, MimiTaskSnapshot } from './mimi-api'
import { reminderStatus } from './reminder-ui'

const fields: Record<string, string> = {
  title: 'Tiêu đề', body_md: 'Nội dung', status: 'Trạng thái', priority: 'Độ ưu tiên',
  pinned: 'Ghim', due_precision: 'Kiểu lịch', due_on: 'Ngày', due_at: 'Ngày và giờ',
}
export const collectionActionLabel = (action: MimiCollectionEntry['command']['action']) =>
  ({ create: 'Tạo Task', edit: 'Sửa', soft_delete: 'Xóa mềm', restore: 'Khôi phục' })[action]
export const reviewFieldLabel = (key: string) => Object.hasOwn(fields, key) ? fields[key] : key

export function reviewValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return 'Không đặt'
  if (value === '') return 'Trống'
  if (key === 'priority' && ['p1', 'p2', 'p3'].includes(String(value))) return String(value).toUpperCase()
  if (key === 'status') return value === 'completed' ? 'Hoàn thành' : value === 'open' ? 'Chưa hoàn thành' : String(value)
  if (key === 'pinned' && typeof value === 'boolean') return value ? 'Đã ghim' : 'Không ghim'
  if (key === 'due_precision') return ({ none: 'Chưa xếp lịch', date: 'Ngày', datetime: 'Ngày + giờ' } as Record<string, string>)[String(value)] ?? String(value)
  if (key === 'due_on' && typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) return value.split('-').reverse().join('/')
  if (key === 'due_at' && typeof value === 'string' && Number.isFinite(Date.parse(value))) {
    return new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3 }).format(new Date(value)) + ' (giờ Việt Nam)'
  }
  return typeof value === 'object' ? 'Giá trị có cấu trúc — xem chi tiết kỹ thuật' : String(value)
}

export type ReviewChild = MimiTaskSnapshot['children'][number]
export function orderedReviewChildren(children: ReviewChild[]) {
  return [...children].sort((a, b) => a.position - b.position || a.id.localeCompare(b.id))
}
export function checklistChanges(entry: MimiCollectionEntry) {
  const before = new Map(entry.before?.children.map((c) => [c.id, c]) ?? [])
  const after = new Map(entry.after.children.map((c) => [c.id, c]))
  return [...new Set([...before.keys(), ...after.keys()])].flatMap((id) => {
    const old = before.get(id), next = after.get(id)
    const changes: string[] = []
    if (!old) changes.push('Thêm mục')
    else if (!next) changes.push('Không còn trong snapshot sau')
    else {
      if (!!old.deleted_at !== !!next.deleted_at) changes.push(next.deleted_at ? 'Xóa mềm mục' : 'Khôi phục mục')
      if (old.content !== next.content) changes.push('Sửa nội dung')
      if (old.is_completed !== next.is_completed) changes.push('Đổi trạng thái hoàn thành')
      if (old.position !== next.position) changes.push('Đổi thứ tự')
    }
    return changes.length ? [{ id, before: old, after: next, changes }] : []
  })
}
export function checklistSummary(entry: MimiCollectionEntry) {
  const active = entry.after.children.filter((c) => !c.deleted_at).length
  const changed = checklistChanges(entry).length
  return changed ? `Checklist thay đổi · ${changed} mục · ${active} mục đang dùng` : `Checklist giữ nguyên · ${active} mục đang dùng`
}
export function reminderEffectLabel(entry: MimiCollectionEntry) {
  const before = entry.before?.reminder ?? entry.reminder_effect.before
  switch (entry.reminder_effect.action) {
    case 'keep': return before ? 'Lời nhắc giữ nguyên' : 'Không có lời nhắc · giữ nguyên'
    case 'none': return 'Không có lời nhắc'
    case 'cancel': return 'Hủy lời nhắc'
    case 'configure': return 'Thiết lập lời nhắc'
    case 'reschedule': return 'Đổi thời điểm nhắc theo lịch mới'
    case 'needs_reschedule': return 'Cần đặt lại giờ nhắc'
    default: return 'Chưa nhận diện hiệu ứng lời nhắc — xem chi tiết kỹ thuật'
  }
}
export function reminderRows(value: Record<string, unknown> | null | undefined) {
  if (!value) return []
  const rows: Array<{ label: string; value: string }> = []
  if (value.status !== undefined) rows.push({ label: 'Trạng thái', value: reminderStatus[String(value.status)] ?? `Chưa nhận diện (${String(value.status)})` })
  if (value.mode !== undefined) rows.push({ label: 'Cách nhắc', value: value.mode === 'absolute' ? 'Thời điểm cụ thể' : value.mode === 'relative' ? 'Theo lịch Task' : String(value.mode) })
  if (value.due_at != null) rows.push({ label: 'Thời điểm nhắc', value: reviewValue('due_at', value.due_at) })
  if (typeof value.offset_minutes === 'number') rows.push({ label: 'Khoảng cách với mốc lịch', value: value.offset_minutes === 0 ? 'Đúng mốc lịch' : `${Math.abs(value.offset_minutes)} phút ${value.offset_minutes < 0 ? 'trước' : 'sau'} mốc lịch` })
  if (value.anchor_time != null) rows.push({ label: 'Giờ mốc cho lịch chỉ có ngày', value: String(value.anchor_time) + ' (giờ Việt Nam)' })
  return rows
}
