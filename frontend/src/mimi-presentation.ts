const runLabels: Record<string, string> = {
  accepted: 'Đã nhận',
  building: 'Đang chuẩn bị',
  running: 'Mimi đang làm việc',
  awaiting_confirmation: 'Chờ bạn xác nhận',
  waiting_confirmation: 'Chờ bạn xác nhận',
  executing: 'Đang ghi thay đổi',
  completed: 'Hoàn tất',
  halted: 'Đã dừng',
  cancelled: 'Đã huỷ',
  retryable: 'Có thể thử lại',
  outcome_unknown: 'Đang đối soát kết quả',
}

export function mimiRunLabel(state: string): string {
  return runLabels[state] ?? 'Trạng thái chưa được nhận diện'
}

type MimiTaskSchedule = {
  due_precision: string
  due_on: string | null
  due_at: string | null
}

function vietnamDateTime(value: string): string {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Ho_Chi_Minh',
    hourCycle: 'h23',
    hour: '2-digit',
    minute: '2-digit',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).formatToParts(new Date(value))
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? '--'
  return `${part('hour')}:${part('minute')} ${part('day')}-${part('month')}-${part('year')}`
}

export function mimiTaskScheduleLabel(task: MimiTaskSchedule): string {
  if (task.due_precision === 'datetime' && task.due_at) return vietnamDateTime(task.due_at)
  if (task.due_precision === 'date' && task.due_on) {
    const [year, month, day] = task.due_on.split('-')
    return `${day}-${month}-${year}`
  }
  return 'Không đặt lịch'
}
