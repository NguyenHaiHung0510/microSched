import { apiRequest } from '@/api'

export type MimiPreviewRange = 'today' | '7d' | '30d' | '3m' | '6m' | '1y'
export type MimiReasoningLevel = 'minimal' | 'balanced' | 'detailed' | 'full'

export type MimiPreviewScenario = {
  id: string
  label: string
  description: string
}

export type MimiPreviewUsagePoint = {
  label: string
  cost: number
  requests: number
  cache_hit_rate: number
}

export type MimiPreviewConversation = {
  id: string
  title: string
  updated_at: string
  archived: boolean
  unread: boolean
  state: string
}

export type MimiPreviewState = {
  synthetic: true
  scenario: string
  scenarios: MimiPreviewScenario[]
  checked_at: string
  usage: {
    range: MimiPreviewRange
    available_ranges: MimiPreviewRange[]
    cost: number
    requests: number
    total_tokens: number
    cached_tokens: number
    cache_hit_rate: number
    source: string
    points: MimiPreviewUsagePoint[]
  }
  route: {
    model: string
    provider: string
    mode: string
    uptime_30d: number
    median_ttft_ms: number
    privacy: string
  }
  run: {
    id: string
    state: 'completed' | 'running' | 'recovering' | 'paused_deadline' | 'awaiting_owner'
    accepted_at: string
    deadline: string
    stage: string
    summary: string
    reasoning: string[]
    tools: Array<{ label: string; state: 'done' | 'running' | 'waiting' }>
    resumable: boolean
  }
  attention: {
    pending_approvals: number
    unresolved_feedback: number
    incidents: number
  }
  health: Array<{
    label: string
    state: 'good' | 'warning' | 'bad' | 'idle'
    detail: string
  }>
  conversations: MimiPreviewConversation[]
}

const PREVIEW_HEADERS = { 'X-Mimi-CSRF': '1' }

export function fetchMimiPreview(range: MimiPreviewRange): Promise<MimiPreviewState> {
  return apiRequest(`/api/mimi/preview?range=${range}`)
}

export function selectMimiPreviewScenario(scenario: string): Promise<MimiPreviewState> {
  return apiRequest('/api/mimi/preview/scenario', {
    method: 'POST',
    headers: PREVIEW_HEADERS,
    body: JSON.stringify({ scenario }),
  })
}
