export type ReminderSource = 'task' | 'event' | 'tracker'
export type Reminder = {
  id: string; source_kind: ReminderSource; source_id: string; source_title: string
  is_private: boolean; source_open: boolean; mode: 'absolute' | 'relative'
  offset_minutes: number | null; anchor_time: string | null; due_at: string
  status: string; revision: number; attempt_count: number; sent_at: string | null
}
export type ReminderSourceInfo = {
  title: string; is_private: boolean; open: boolean; anchor_at: string | null
  anchor_day: string | null; date_only: boolean
  updated_at?: string
}
export const reminderKey = ['reminders'] as const
export const activeReminder = (r: Reminder) => ['pending', 'sending', 'needs_reschedule'].includes(r.status)
export const reminderStatus: Record<string, string> = {
  pending: 'Đang chờ', sending: 'Đang gửi', sent: 'Đã gửi tới dịch vụ thông báo',
  needs_reschedule: 'Cần đặt lại giờ', missed: 'Lỡ thời điểm nhắc', no_device: 'Chưa có thiết bị nhận',
  failed: 'Chưa xác nhận gửi thành công', cancelled: 'Đã huỷ',
}
export function reminderTime(value: string): string {
  return new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh',
    weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}
export function vnInput(value: string): string {
  return new Date(Date.parse(value) + 7 * 3600000).toISOString().slice(0, 16)
}
export function reminderPreview(source: ReminderSourceInfo, mode: string, absolute: string,
  amount: string, unit: string, direction: string, clock: string): string | null {
  const offset = Number(amount) * Number(unit) * Number(direction)
  if (mode === 'relative' && (!amount || Number(amount) < 0 || !Number.isInteger(offset) || Math.abs(offset) > 525600)) return null
  const anchor = source.date_only
    ? (clock && (source.anchor_day || (source.anchor_at && vnInput(source.anchor_at).slice(0, 10))))
      ? `${source.anchor_day || vnInput(source.anchor_at!).slice(0, 10)}T${clock}+07:00` : ''
    : source.anchor_at || ''
  const value = mode === 'absolute' ? Date.parse(`${absolute}+07:00`) : Date.parse(anchor) + offset * 60000
  return Number.isFinite(value) ? new Date(value).toISOString() : null
}
