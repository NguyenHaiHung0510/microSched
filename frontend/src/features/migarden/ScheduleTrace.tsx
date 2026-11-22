import type { ConfigView } from './api'
import { scheduleLabel } from './presentation'

export function ScheduleTrace({ config }: { config: ConfigView }) {
  const pending = config.application_status !== 'applied' && config.desired
  if (!pending) return null
  const paused = !config.desired!.schedule.enabled
  return <div className="space-y-1 rounded-lg bg-accent p-3 text-sm" role="status">
    <p className="font-bold">{config.application_status === 'rejected' ? 'ESP báo chưa áp dụng được bản đã lưu'
      : paused ? 'Đã lưu tạm dừng · Chờ ESP xác nhận' : 'Đã lưu lịch · Chờ ESP xác nhận'}</p>
    {config.applied ? <p>Bản ESP xác nhận gần nhất: {scheduleLabel(config.applied.schedule)}.</p>
      : <p>Chưa có bản lịch được ESP xác nhận.</p>}
    {paused && config.applied?.schedule.enabled && <p>Tạm dừng đã lưu chưa xác nhận đầu ra ở tủ đã tắt.</p>}
  </div>
}
