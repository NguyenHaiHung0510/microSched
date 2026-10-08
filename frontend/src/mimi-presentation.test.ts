import { describe, expect, it } from 'vitest'

import {
  mimiFeedbackTargets,
  resolveCancelAcknowledgment,
  mimiTaskScheduleLabel,
  resolveMimiFeedbackTarget,
} from '@/mimi-presentation'

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

describe('mimiFeedbackTargets', () => {
  it('distinguishes calls when two runs each have an unknown first attempt', () => {
    const source = {
      messages: [],
      runs: [
        { id: 'deadline-run', generation: 7, state: 'deadline_exceeded' },
        { id: 'cancelled-run', generation: 8, state: 'cancelled' },
      ],
      provider_calls: [
        { id: 'deadline-call', run_id: 'deadline-run', attempt: 1, state: 'unknown' },
        { id: 'cancelled-call', run_id: 'cancelled-run', attempt: 1, state: 'unknown' },
      ],
      receipts: [],
    }
    const calls = mimiFeedbackTargets(source).filter((target) => target.target_type === 'call')
    expect(new Set(calls.map((target) => target.label)).size).toBe(2)
    expect(calls).toEqual([
      { target_type: 'call', target_id: 'deadline-call', label: 'Run 7 · Lần gọi 1 · chưa rõ kết quả' },
      { target_type: 'call', target_id: 'cancelled-call', label: 'Run 8 · Lần gọi 2 · chưa rõ kết quả' },
    ])
  })

  it('offers an answer target when a text-only conversation has no receipt', () => {
    expect(mimiFeedbackTargets({
      messages: [
        { id: 'user-turn', role: 'user', sequence: 1 },
        { id: 'answer-turn', role: 'assistant', sequence: 2 },
      ],
      runs: [{ id: 'failed-run', generation: 1, state: 'halted' }],
      provider_calls: [{ id: 'failed-call', attempt: 1, state: 'failed' }],
      receipts: [],
    })).toEqual([
      { target_type: 'turn', target_id: 'answer-turn', label: 'Câu trả lời · lượt 2' },
      { target_type: 'run', target_id: 'failed-run', label: 'Run 1 · Đã dừng' },
      { target_type: 'call', target_id: 'failed-call', label: 'Lần gọi 1 · thất bại' },
    ])
  })

  it('offers receipt feedback when a receipt exists alongside answer/run/call targets', () => {
    const targets = mimiFeedbackTargets({
      messages: [{ id: 'answer-turn', role: 'assistant', sequence: 4 }],
      runs: [{ id: 'run', generation: 2, state: 'completed' }],
      provider_calls: [{ id: 'call', attempt: 2, state: 'succeeded' }],
      receipts: [{ id: 'receipt' }],
    })

    expect(targets.map(({ target_type }) => target_type)).toEqual(['turn', 'run', 'call', 'receipt'])
    expect(targets.at(-1)).toEqual({ target_type: 'receipt', target_id: 'receipt', label: 'Receipt 1' })
  })
})

describe('resolveMimiFeedbackTarget', () => {
  const target = { target_type: 'turn' as const, target_id: 'answer-1', label: 'Answer' }

  it('does not silently fall back when the bound target disappears', () => {
    expect(resolveMimiFeedbackTarget(
      [],
      'turn:answer-1',
      'conversation-1',
      true,
      { conversationId: 'conversation-1', targetKey: 'turn:answer-1' },
    )).toBeNull()
  })

  it('keeps a draft unbound across a conversation switch until an explicit target choice', () => {
    expect(resolveMimiFeedbackTarget(
      [target],
      'turn:answer-1',
      'conversation-2',
      true,
      { conversationId: 'conversation-1', targetKey: 'turn:answer-1' },
    )).toBeNull()
    expect(resolveMimiFeedbackTarget(
      [target],
      'turn:answer-1',
      'conversation-2',
      true,
      { conversationId: 'conversation-2', targetKey: 'turn:answer-1' },
    )).toEqual(target)
  })
})

describe('resolveCancelAcknowledgment', () => {
  it('preserves unknown-outcome reconciliation after a late cancelling acknowledgment', () => {
    expect(resolveCancelAcknowledgment(
      'run-cancelled',
      'run-cancelled',
      { id: 'run-cancelled', state: 'cancelled', provider_outcome: 'unknown' },
      'cancelling',
    )).toEqual({
      apply: false,
      stage: 'Kết quả chưa xác định · cần đối soát',
      clearActiveRun: true,
      needsReconcile: true,
    })
  })

  it('keeps a terminal canceled stream authoritative over its late cancel acknowledgment', () => {
    expect(resolveCancelAcknowledgment(
      'run-cancelled',
      null,
      { id: 'run-cancelled', state: 'cancelled', provider_outcome: 'unknown' },
      'cancelling',
    )).toEqual({
      apply: false,
      stage: 'Kết quả chưa xác định · cần đối soát',
      clearActiveRun: false,
      needsReconcile: true,
    })
  })

  it('does not let an old cancel acknowledgment overwrite a newer run', () => {
    expect(resolveCancelAcknowledgment(
      'old-run',
      'new-run',
      { id: 'new-run', state: 'running', provider_outcome: null },
      'cancelling',
    )).toEqual({ apply: false, stage: null, clearActiveRun: false, needsReconcile: false })
  })
})
