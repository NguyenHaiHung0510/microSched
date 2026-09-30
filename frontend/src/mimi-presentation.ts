import type { MimiFeedbackTarget } from '@/mimi-api'

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
  deadline_exceeded: 'Hết thời gian run',
  budget_exceeded: 'Chạm giới hạn context',
}

export function mimiFeedbackTargets(source: {
  messages: Array<{ id: string; role: string; sequence: number }>
  runs: Array<{ id: string; generation: number; state: string }>
  provider_calls?: Array<{ id: string; attempt: number; state: string }> | null
  receipts: Array<{ id: string }>
}): MimiFeedbackTarget[] {
  return [
    ...source.messages
      .filter((message) => message.role === 'assistant')
      .map((message) => ({
        target_type: 'turn' as const,
        target_id: message.id,
        label: `Câu trả lời · lượt ${message.sequence}`,
      })),
    ...source.runs.map((run) => ({
      target_type: 'run' as const,
      target_id: run.id,
      label: `Run ${run.generation} · ${mimiRunLabel(run.state)}`,
    })),
    ...(source.provider_calls ?? []).map((call) => ({
      target_type: 'call' as const,
      target_id: call.id,
      label: `Lần gọi ${call.attempt} · ${({
        intent: 'đang chuẩn bị',
        dispatched: 'đã gửi',
        succeeded: 'hoàn tất',
        failed: 'thất bại',
        unknown: 'chưa rõ kết quả',
        fenced: 'đã chặn',
      } as Record<string, string>)[call.state] ?? 'chưa rõ trạng thái'}`,
    })),
    ...source.receipts.map((receipt, index) => ({
      target_type: 'receipt' as const,
      target_id: receipt.id,
      label: `Receipt ${index + 1}`,
    })),
  ]
}

export function resolveMimiFeedbackTarget(
  targets: MimiFeedbackTarget[],
  selectedKey: string,
  conversationId: string,
  hasDraft: boolean,
  binding: { conversationId: string; targetKey: string } | null,
): MimiFeedbackTarget | null {
  const selected = targets.find(
    (target) => `${target.target_type}:${target.target_id}` === selectedKey,
  )
  if (!hasDraft) return selected ?? targets[0] ?? null
  if (!binding || binding.conversationId !== conversationId || binding.targetKey !== selectedKey) {
    return null
  }
  return selected ?? null
}

export function mimiTerminalRunStage(state: string, providerOutcome: string | null): string {
  if (state === 'cancelled' && providerOutcome === 'unknown') {
    return 'Kết quả chưa xác định · cần đối soát'
  }
  const terminalLabels: Record<string, string> = {
    completed: 'Đã hoàn tất',
    waiting_confirmation: 'Chờ bạn xác nhận',
    cancelled: 'Đã huỷ run',
    halted: 'Run đã dừng',
    retryable: 'Run có thể tiếp tục',
    outcome_unknown: 'Kết quả chưa xác định · cần đối soát',
    deadline_exceeded: 'Run đã hết thời gian',
    budget_exceeded: 'Run đã chạm giới hạn',
  }
  return terminalLabels[state] ?? mimiRunLabel(state)
}

export function resolveCancelAcknowledgment(
  targetRunId: string,
  displayedRunId: string | null,
  latestRun: { id: string; state: string; provider_outcome: string | null } | null,
  responseState: string,
): { apply: boolean; stage: string | null; clearActiveRun: boolean; needsReconcile: boolean } {
  const matchesLatest = !latestRun || latestRun.id === targetRunId
  const latestIsTerminal = !!latestRun && matchesLatest && [
    'waiting_confirmation', 'completed', 'halted', 'cancelled', 'retryable',
    'outcome_unknown', 'deadline_exceeded', 'budget_exceeded',
  ].includes(latestRun.state)
  // A null display ref is safe only when the latest snapshot proves this same
  // run is terminal. Otherwise a late callback could label an unrelated state.
  const matchesDisplay = displayedRunId === targetRunId
    || (displayedRunId === null && latestIsTerminal)
  const needsReconcile = !!latestRun && matchesLatest && (
    latestRun.state === 'outcome_unknown'
    || latestRun.state === 'deadline_exceeded'
    || (latestRun.state === 'cancelled' && latestRun.provider_outcome === 'unknown')
  )

  if (!matchesLatest || !matchesDisplay || latestIsTerminal) {
    return {
      apply: false,
      stage: latestIsTerminal && latestRun
        ? mimiTerminalRunStage(latestRun.state, latestRun.provider_outcome)
        : null,
      clearActiveRun: displayedRunId === targetRunId,
      needsReconcile,
    }
  }

  if (responseState === 'cancelling') {
    return {
      apply: true,
      stage: 'Đang huỷ theo yêu cầu',
      clearActiveRun: displayedRunId === targetRunId,
      needsReconcile: false,
    }
  }
  return {
    apply: true,
    stage: mimiTerminalRunStage(responseState, latestRun?.provider_outcome ?? null),
    clearActiveRun: displayedRunId === targetRunId,
    needsReconcile,
  }
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
