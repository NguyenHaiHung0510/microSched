import type { MimiConversation } from '@/mimi-api'
import { responseSeconds } from '@/mimi-response-timing'

export function MimiResponseTiming({ conversation, targetId }: { conversation: MimiConversation; targetId: string }) {
  const timing = conversation.response_timings?.responses.find(row => row.target_id === targetId)
  const cost = conversation.metrics?.responses.find(row => row.run_id === timing?.run_id)
  return <p className="text-xs text-muted-foreground tabular-nums" data-testid="mimi-answer-timing">
    E2E {responseSeconds(timing?.elapsed_ms)}{timing?.phase === 'confirmation' ? ' · sau xác nhận' : timing?.phase === 'resume' ? ' · tiếp tục' : ''}
    {timing && timing.outcome !== 'succeeded' ? ` · ${timing.outcome === 'cancelled' ? 'đã huỷ' : timing.outcome === 'pending' ? 'đang chờ' : 'chưa thành công'}` : ''}
    {timing?.elapsed_ms == null ? ` · ${timing?.observation === 'hidden' ? 'ẩn trong lúc đo' : timing?.observation === 'offscreen' ? 'ngoài vùng nhìn' : 'chưa có phép đo browser'}` : ''}
    {' · '}USD {cost?.usd.known == null ? '—' : `$${cost.usd.known}`}{cost && !cost.usd.complete ? ' đã biết, chưa đủ' : ''} · phí cùng run, không cộng lại
  </p>
}
