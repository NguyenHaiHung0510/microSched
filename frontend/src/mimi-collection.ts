import type { MimiChangeSet, MimiCollectionEntry, MimiCollectionPlan, MimiSelection } from './mimi-api'

export function collectionConfirmationNotice(change: MimiChangeSet): string | null {
  if (change.confirmation_preflight?.status === 'eligible') return null
  const reason = change.confirmation_preflight?.reason
  if (reason === 'change_set_frontier_stale') return 'Preview vẫn được giữ để xem, nhưng hội thoại đã thay đổi. Hãy yêu cầu Mimi lập phương án mới trước khi xác nhận.'
  if (reason === 'change_set_stale') return 'Preview vẫn được giữ để xem nhưng không còn hợp lệ để xác nhận. Hãy yêu cầu Mimi lập phương án mới.'
  if (reason === 'change_set_expired') return 'Preview đã hết hạn. Hãy yêu cầu Mimi lập phương án mới.'
  if (!change.confirmation_preflight) return 'Chưa có trạng thái xác nhận từ server. Hãy đọc lại hội thoại trước khi xác nhận.'
  return 'Server chưa cho phép xác nhận preview này. Hãy đọc lại hội thoại và yêu cầu phương án mới nếu cần.'
}

export const MIMI_REVIEW_PAGE_SIZE = 20
export function mimiChangeTitle(change: MimiChangeSet): string {
  return change.operation.tool === 'task.collection.v1'
    ? `${change.operation.args.entries.length} Task${change.operation.args.undo_receipt_id ? ' · hoàn tác' : ''}`
    : change.operation.args.title
}
export function collectionPage(plan: MimiCollectionPlan, query: string, classification: string, selection: MimiSelection | undefined, page: number) {
  const members = new Map(selection?.members.map((m) => [m.id, m]) ?? [])
  const needle = query.trim().toLocaleLowerCase('vi-VN')
  const entries = plan.entries.filter((entry) => {
    const label = `${entry.id} ${String(entry.after.fields.title ?? '')} ${String(entry.before?.fields.title ?? '')}`.toLocaleLowerCase('vi-VN')
    return (!needle || label.includes(needle)) && (classification === 'all' || (members.get(entry.id)?.classification ?? 'included') === classification)
  })
  const pageCount = Math.max(1, Math.ceil(entries.length / MIMI_REVIEW_PAGE_SIZE))
  const currentPage = Math.max(0, Math.min(page, pageCount - 1))
  return { entries: entries.slice(currentPage * MIMI_REVIEW_PAGE_SIZE, (currentPage + 1) * MIMI_REVIEW_PAGE_SIZE), visibleCount: entries.length, pageCount, currentPage }
}
export function collectionCounts(plan: MimiCollectionPlan, selection: MimiSelection | undefined) {
  return {
    affected: plan.entries.length,
    included: selection ? selection.members.filter((m) => m.classification === 'included').length : plan.entries.length,
    excluded: selection?.members.filter((m) => m.classification === 'excluded').length ?? 0,
    uncertain: selection?.members.filter((m) => m.classification === 'uncertain').length ?? 0,
  }
}
export function collectionFieldDiff(entry: MimiCollectionEntry) {
  const keys = new Set([...Object.keys(entry.before?.fields ?? {}), ...Object.keys(entry.after.fields)])
  return [...keys].filter((key) => JSON.stringify(entry.before?.fields[key] ?? null) !== JSON.stringify(entry.after.fields[key] ?? null)).map((key) => ({ key, before: entry.before?.fields[key] ?? null, after: entry.after.fields[key] ?? null }))
}

export function collectionConfirmable(plan: MimiCollectionPlan, selection: MimiSelection | undefined) {
  if (!plan.selection_id) return true // Server-frozen create or versioned inverse.
  if (!selection || selection.selection_id !== plan.selection_id) return false
  const included = new Set(selection.members.filter((m) => m.classification === 'included').map((m) => m.id))
  if (included.size !== plan.entries.length || plan.entries.some((entry) => !included.has(entry.id))) return false
  return selection.explicitly_named_subset || (selection.query_complete && selection.semantic_complete && !selection.members.some((m) => m.classification === 'uncertain'))
}
