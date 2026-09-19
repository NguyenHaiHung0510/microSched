import { describe, expect, it } from 'vitest'

import { mimiTaskScheduleLabel } from '@/mimi-presentation'

describe('mimiTaskScheduleLabel', () => {
  it('shows the Task schedule separately from preview expiry', () => {
    expect(
      mimiTaskScheduleLabel({
        due_precision: 'datetime',
        due_on: null,
        due_at: '2026-09-20T21:00:00+07:00',
      }),
    ).toBe('21:00 20-09-2026')
    expect(
      mimiTaskScheduleLabel({
        due_precision: 'date',
        due_on: '2026-09-21',
        due_at: null,
      }),
    ).toBe('21-09-2026')
    expect(
      mimiTaskScheduleLabel({ due_precision: 'none', due_on: null, due_at: null }),
    ).toBe('Không đặt lịch')
  })
})
