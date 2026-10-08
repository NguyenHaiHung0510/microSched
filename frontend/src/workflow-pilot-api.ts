import { apiRequest } from '@/api'

const ROOT = '/api/mimi/workflow-pilot'
const WRITE_HEADERS = { 'X-Mimi-CSRF': '1' }

export type WorkflowPilotTask = { id: string; title: string }
export type WorkflowPilotStatus = {
  run_id: string
  generation: number
  engine: 'graph' | 'control'
  provider_mode: 'deterministic' | string
  phase: 'query' | 'group' | 'draft' | 'direction' | 'materialize' | 'confirmation' | 'execute' | 'succeeded' | 'expired' | 'cancelled' | 'reconcile' | 'repreview' | string
  draft: string | null
  preview_digest: string | null
  preview: {
    sources: Array<{ id: string; version: number | string; title: string }>
    operations: Array<{ id: string; title: string }>
    groups: string[][]
  } | null
  receipt: { digest: string; changed: number } | null
  stop_reason: string | null
  provider_calls: number
  events: string[]
  invocation_active?: boolean
  can_resume?: boolean
  can_cancel?: boolean
  source_visibility_reason?: string
}
const json = (value: unknown) => JSON.stringify(value)

export const listWorkflowPilotTasks = () => apiRequest<{ items: WorkflowPilotTask[] }>(`${ROOT}/tasks`)
export const listWorkflowPilotRuns = () => apiRequest<{ items: WorkflowPilotStatus[] }>(`${ROOT}/runs`)
export const getWorkflowPilotRun = (runId: string) => apiRequest<WorkflowPilotStatus>(`${ROOT}/runs/${encodeURIComponent(runId)}`)

export function createWorkflowPilotRun(runId: string, taskIds: string[], engine: 'graph' | 'control') {
  return apiRequest<WorkflowPilotStatus>(`${ROOT}/runs`, {
    method: 'POST', headers: WRITE_HEADERS, body: json({ run_id: runId, task_ids: taskIds, engine }),
  })
}

export function advanceWorkflowPilotRun(
  run: WorkflowPilotStatus,
  action: { direction: 'apply_prefix' } | { preview_digest: string } | { cancel: true } | { resume: true },
) {
  return apiRequest<WorkflowPilotStatus>(`${ROOT}/runs/${encodeURIComponent(run.run_id)}/advance`, {
    method: 'POST', headers: WRITE_HEADERS, body: json({ generation: run.generation, ...action }),
  })
}
