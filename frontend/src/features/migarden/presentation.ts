import { ApiError } from '@/api'
import type { GardenState, HistoryItem, Source } from './api'

export const sources: Record<Source, string> = {
  schedule: 'Theo lịch', remote: 'Từ web', local_button: 'Tại nút',
}
const tz = 'Asia/Ho_Chi_Minh'
const shortDate = new Intl.DateTimeFormat('vi-VN', { timeZone: tz, day: '2-digit', month: '2-digit' })
const shortTime = new Intl.DateTimeFormat('vi-VN', { timeZone: tz, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
const wallClock = new Intl.DateTimeFormat('en-CA', {
  timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})
export const dateLabel = (at: string) => shortDate.format(new Date(at))
export const timeLabel = (at: string) => shortTime.format(new Date(at))
export const instantLabel = (at: string) => dateLabel(at) + ' · ' + timeLabel(at)
export const dayLabel = (day: string) => day.slice(8, 10) + '/' + day.slice(5, 7)
export const duration = (seconds: number) =>
  [Math.floor(seconds / 60) ? Math.floor(seconds / 60) + ' phút' : '',
    seconds % 60 || !seconds ? seconds % 60 + ' giây' : ''].filter(Boolean).join(' ')
export const stopwatch = (seconds: number) =>
  [Math.floor(seconds / 60), seconds % 60].map(unit => String(unit).padStart(2, '0')).join(':')
export const localInput = (at: string) => {
  const parts = Object.fromEntries(wallClock.formatToParts(new Date(at)).map(part => [part.type, part.value]))
  return parts.year + '-' + parts.month + '-' + parts.day + 'T' + parts.hour + ':' + parts.minute
}
export function fromLocal(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) throw new Error('Chọn giờ Hà Nội đến phút.')
  const at = new Date(value + ':00+07:00')
  if (!Number.isFinite(at.getTime()) || localInput(at.toISOString()) !== value) throw new Error('Ngày hoặc giờ không hợp lệ.')
  return at.toISOString()
}

export function displayedSession(state: GardenState, received: number, now: number, online: boolean) {
  const session = state.snapshot?.active_session
  const snapshotAgeAtLoad = state.snapshot_received_at
    ? Date.parse(state.server_time) - Date.parse(state.snapshot_received_at) : Infinity
  const observedAge = state.snapshot?.observed_at
    ? Date.parse(state.server_time) - Date.parse(state.snapshot.observed_at) : Infinity
  const age = Math.max(0, now - received)
  const fresh = online && state.connection === 'fresh' && snapshotAgeAtLoad + age <= 45_000
  const live = fresh && Boolean(session) && state.snapshot?.output === 'on' &&
    state.snapshot.time_quality !== 'unknown' && observedAge + age <= 45_000
  const reported = session?.elapsed_seconds ?? 0
  const elapsed = live && session
    ? Math.max(reported, Math.min(session.duration_seconds, reported + Math.floor(Math.max(0, observedAge + age) / 1000)))
    : reported
  return { fresh, live, elapsed }
}

const reasonLabels: Record<string, string> = {
  controller_not_provisioned: 'Chưa kết nối Controller với Khu A.',
  controller_revoked: 'Kết nối Controller đã bị thu hồi.',
  controller_boot_unknown: 'Chưa có lần kết nối để xác định Controller nhận lệnh.',
  device_waiting: 'Đang chờ báo cáo đầu tiên từ Controller.',
  device_stale: 'Báo cáo quá cũ. Đợi Controller đồng bộ để tưới từ web.',
  busy: 'Controller đang xử lý một lượt tưới.',
  unresolved_execution: 'Chưa rõ kết quả lượt trước. Chờ báo cáo và kiểm tra tại tủ.',
  output_unknown: 'Chưa rõ trạng thái đầu ra.',
  clock_or_observation_untrusted: 'Giờ hoặc báo cáo của Controller chưa đủ tin cậy.',
  controller_not_ready: 'Controller chưa sẵn sàng. Kiểm tra tại tủ.',
  config_unconfirmed: 'Chưa xác nhận cấu hình Controller đang dùng.',
  start_pending: 'Đang chuyển yêu cầu tưới. Theo dõi kết quả trước khi gửi tiếp.',
  stop_pending: 'Yêu cầu Dừng đang chờ Controller xử lý.',
  config_conflict: 'Cấu hình đã thay đổi ở nơi khác. Bản nhập vẫn còn; kiểm tra bản mới rồi lưu lại.',
  preview_missing: 'Bản xem trước không còn hiệu lực. Hãy xem trước lại.',
  preview_expired: 'Bản xem trước đã hết hạn. Hãy xem trước lại.',
  preview_context_changed: 'Controller hoặc cấu hình đã thay đổi. Hãy xem trước lại.',
  duration_exceeds_applied_limit: 'Thời lượng vượt giới hạn mỗi lượt đã áp dụng.',
  migarden_invalid_payload: 'Kiểm tra ngày giờ, thời lượng và giới hạn rồi thử lại.',
  canceled_by_stop: 'Lệnh Dừng đã hủy yêu cầu chưa được cấp quyền.',
  expired_before_grant: 'Hết hạn trước khi cấp quyền tưới.',
  grant_outcome_unknown: 'Đã cấp quyền, chưa có báo cáo kết quả. Kiểm tra tại tủ.',
  stop_outcome_unconfirmed: 'Chưa xác nhận Controller đã nhận lệnh Dừng.',
  context_changed: 'Bối cảnh Controller đã đổi; yêu cầu cũ không được cấp quyền.',
  new_boot_reported_off: 'Controller đã khởi động lại và báo đầu ra tắt; chưa xác nhận lệnh Dừng cũ.',
  close_requested: 'Controller đã yêu cầu tắt đầu ra.',
  already_off: 'Controller báo đầu ra đã tắt.',
}
export function explainReason(code: string | null | undefined): string | null {
  return code ? (reasonLabels[code] ?? code) : null
}
export function errorText(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    const detail = (error.body as { detail?: string | { code?: string } } | null)?.detail
    const code = typeof detail === 'string' ? detail : detail?.code
    if (code && reasonLabels[code]) return reasonLabels[code]
    if (error.status === 503) return 'Chưa kết nối được dữ liệu. Thử lại khi dịch vụ sẵn sàng.'
  }
  return fallback
}
export const statusLabels: Record<string, string> = {
  pending: 'Chờ Controller nhận',
  received: 'Controller đã nhận bản lệnh',
  granted: 'Đã cấp quyền · Chưa xác nhận chạy',
  started: 'Có báo cáo đã bắt đầu',
  rejected: 'Bị từ chối',
  canceled: 'Đã hủy trước cấp quyền',
  expired: 'Hết hạn trước cấp quyền',
  unknown: 'Chưa rõ kết quả',
  completed: 'Đã kết thúc',
  stopped: 'Đã dừng theo báo cáo',
  fault: 'Lỗi khi tưới',
  stop_requested: 'Đã gửi yêu cầu Dừng',
  stop_received: 'Controller đã nhận yêu cầu Dừng',
  stop_confirmed: 'Controller đã xử lý Dừng',
  stop_stale: 'Lệnh Dừng thuộc lần khởi động cũ',
  stop_unconfirmed: 'Chưa xác nhận Dừng',
  skipped: 'Bỏ qua cơ hội lịch',
  close_requested: 'Đã yêu cầu tắt đầu ra',
  already_off: 'Đầu ra đã tắt theo báo cáo',
  unconfirmed: 'Chưa xác nhận Dừng',
}
export function historyLabel(item: HistoryItem): string {
  if (item.kind === 'remote_stop' || item.kind === 'stop_processed') return 'Dừng tưới'
  if (item.kind === 'session_started' || item.kind === 'remote_start') return 'Bắt đầu tưới'
  if (item.kind === 'session_ended') return 'Kết quả lượt tưới'
  if (item.kind === 'occurrence_decided') return 'Cơ hội lịch'
  return 'Yêu cầu bị từ chối'
}
