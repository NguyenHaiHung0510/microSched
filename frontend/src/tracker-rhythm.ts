export type ActivityDay = { tracker_id: string; day: string; count: number }

export function daysInReportMonth(month: string): string[] {
  const match = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(month)
  if (!match) return []
  const year = Number(match[1])
  const monthNumber = Number(match[2])
  const days = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate()
  return Array.from({ length: days }, (_, index) => `${month}-${String(index + 1).padStart(2, '0')}`)
}

/** Monday-first offset for the report month's calendar grid. */
export function reportMonthOffset(month: string): number {
  const match = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(month)
  if (!match) return 0
  return (new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, 1)).getUTCDay() + 6) % 7
}

export function activityCountByTrackerDay(rows: ActivityDay[]): Map<string, number> {
  const counts = new Map<string, number>()
  for (const row of rows) {
    if (row.count > 0) counts.set(`${row.tracker_id}:${row.day}`, row.count)
  }
  return counts
}

export function isFutureActivityDay(day: string, now = new Date()): boolean {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now)
  const value = (type: Intl.DateTimeFormatPartTypes) => parts.find((part) => part.type === type)?.value ?? ''
  const today = `${value('year')}-${value('month')}-${value('day')}`
  return day > today
}
