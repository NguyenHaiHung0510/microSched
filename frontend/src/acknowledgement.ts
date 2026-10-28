import { ApiError } from '@/api'

const uncertainCommits = new Set([
  'mimi_response_timing_commit_unknown', 'mimi_feedback_commit_unknown',
  'note_move_to_top_commit_unknown', 'history_handled_commit_unknown',
  'history_batch_prepare_commit_unknown', 'history_batch_commit_unknown',
])

/** The six opt-in ACK boundaries cannot promise that a lost commit saved nothing. */
export function commitOutcomeMessage(error: unknown): string | null {
  return error instanceof ApiError && error.status === 503 && uncertainCommits.has(error.message)
    ? 'Chưa xác định kết quả lưu trên máy chủ. Giữ nguyên nội dung và mục đã chọn; thử lại yêu cầu cũ để đối chiếu.'
    : null
}
