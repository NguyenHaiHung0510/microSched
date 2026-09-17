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
