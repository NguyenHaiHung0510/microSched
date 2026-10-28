import type { MimiResponseTiming, MimiResponseTimingInput } from '@/mimi-api'

export const MAX_RESPONSE_ELAPSED_MS = 86_400_000
export type ResponseStart = {
  conversationId: string
  sourceId: string
  runId: string | null
  phase: MimiResponseTimingInput['phase']
  started: number
  hidden: boolean
}

/** A document-local clock never resumes from storage or server timestamps. */
export class MimiResponseClock {
  starts = new Map<string, ResponseStart>()
  receipts = new Map<string, { conversationId: string; body: MimiResponseTimingInput; state: 'ready' | 'sending' | 'saved' | 'unknown' }>()

  begin(start: ResponseStart) {
    this.starts.set(JSON.stringify([start.conversationId, start.phase, start.sourceId]), start)
  }
  bind(conversationId: string, phase: ResponseStart['phase'], sourceId: string, runId: string) {
    const start = this.starts.get(JSON.stringify([conversationId, phase, sourceId]))
    if (start) start.runId = runId
  }
  hide() { for (const start of this.starts.values()) start.hidden = true }
  hideConversation(conversationId: string) { for (const start of this.starts.values()) if (start.conversationId === conversationId) start.hidden = true }
  candidates(conversationId: string, responses: MimiResponseTiming[]) {
    return responses.flatMap(response => {
      if (!response.source_id || response.outcome === 'pending' || response.observation !== 'missing') return []
      const start = this.starts.get(JSON.stringify([conversationId, response.phase, response.source_id]))
      const key = JSON.stringify([conversationId, response.target_id, response.phase])
      if (!start || start.runId !== response.run_id || this.receipts.has(key)) return []
      return [{ response, start, key }]
    })
  }
  complete(key: string, start: ResponseStart, response: MimiResponseTiming, now: number, observation: MimiResponseTimingInput['observation']) {
    if (this.receipts.has(key)) return
    const elapsed = now - start.started
    if (!Number.isFinite(elapsed) || elapsed < 0 || elapsed > MAX_RESPONSE_ELAPSED_MS) return
    const body: MimiResponseTimingInput = {
      version: 1, client_id: crypto.randomUUID(), run_id: response.run_id,
      target_id: response.target_id, phase: response.phase, source_id: start.sourceId,
      observation, elapsed_ms: observation === 'visible_paint' ? Math.round(elapsed * 1000) / 1000 : null,
    }
    this.receipts.set(key, { conversationId: start.conversationId, body, state: 'ready' })
    this.starts.delete(JSON.stringify([start.conversationId, start.phase, start.sourceId]))
  }
}

export function responseSeconds(milliseconds: number | null | undefined) {
  return milliseconds == null ? '—' : `${(milliseconds / 1000).toLocaleString('vi-VN', { maximumFractionDigits: 2 })} giây`
}

export function responseOutcomeLabel(outcome: MimiResponseTiming['outcome']) {
  return { succeeded: 'hoàn tất', failed: 'thất bại', cancelled: 'đã huỷ', unknown: 'chưa rõ', pending: 'đang chờ' }[outcome]
}
