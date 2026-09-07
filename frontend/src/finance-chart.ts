/** Zero stays zero; negative values extend left of a shared zero baseline. */
export function financeBarScale(values: number[]) {
  const finite = values.filter(Number.isFinite)
  const minimum = Math.min(0, ...finite)
  const maximum = Math.max(0, ...finite)
  const range = maximum - minimum
  const zero = minimum < 0 && range > 0 ? (-minimum / range) * 100 : 0
  return {
    zero,
    signed: minimum < 0,
    bar(value: number) {
      if (!Number.isFinite(value) || range === 0) return { left: zero, width: 0 }
      const endpoint = ((value - minimum) / range) * 100
      return { left: Math.min(zero, endpoint), width: Math.abs(endpoint - zero) }
    },
  }
}

/** A signed or empty total cannot be described as parts of a positive whole. */
export function financeShares(values: number[]): number[] | null {
  if (values.some((value) => !Number.isFinite(value) || value < 0)) return null
  const total = values.reduce((sum, value) => sum + value, 0)
  return total > 0 ? values.map((value) => (value / total) * 100) : null
}

/** Backend finance windows are half-open ISO-8601 boundaries. */
export function financePeriodLabel(start: string | null, end: string | null) {
  if (!start || !end) return 'Chưa có kỳ so sánh'
  const startAt = new Date(start)
  const endAt = new Date(end)
  if (!Number.isFinite(startAt.getTime()) || !Number.isFinite(endAt.getTime())) {
    return 'Không rõ thời gian'
  }
  const date = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit', year: 'numeric' })
  const time = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit' })
  return endAt <= startAt ? 'Kỳ chưa bắt đầu' : `${date.format(startAt)} → trước ${time.format(endAt)} ${date.format(endAt)}`
}

export function financePeriodLabels(start: string, end: string, previousStart: string | null, previousEnd: string | null) {
  return {
    current: financePeriodLabel(start, end),
    previous: financePeriodLabel(previousStart, previousEnd),
  }
}
