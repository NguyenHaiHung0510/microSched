import { apiRequest } from '@/api'
import { useQuery } from '@tanstack/react-query'

export type Source = 'schedule' | 'remote' | 'local_button'
export type Recurrence =
  | { kind: 'once'; at: string }
  | { kind: 'daily'; at_local_time: string }
  | { kind: 'weekly'; at_local_time: string; days_of_week: number[] }
  | { kind: 'interval'; anchor_at: string; interval_minutes: number }
export type Policy = {
  manual_duration_seconds: number
  max_session_seconds: number
  max_window_seconds: number
  window_seconds: 10800
}
export type Schedule = {
  enabled: boolean
  effective_from: string
  effective_until: string | null
  duration_seconds: number
  recurrence: Recurrence
}
export type Bundle = { policy: Policy; schedule: Schedule }
export type Config = Bundle & { zone_id: string; binding_ref: string; config_ref: string }
export type ConfigView = {
  desired: Config | null
  desired_saved_at: string | null
  applied: Config | null
  applied_confirmed_at: string | null
  application_status: 'not_saved' | 'pending' | 'applied' | 'rejected'
  reason: string | null
}
export type Session = {
  session_id: string
  request_id: string | null
  trigger_source: Source
  started_at: string | null
  duration_seconds: number
  elapsed_seconds: number
  config_ref: string
}
export type Command = {
  request_id: string
  kind: 'start' | 'stop'
  status: string
  reason: string | null
  confirmed_at: string
  expires_at: string | null
  duration_seconds: number | null
  config_ref: string | null
}
export type Forecast = {
  status: 'no_applied_config' | 'paused' | 'no_future_occurrence' | 'scheduled'
  config_ref: string | null
  next_at: string | null
  day: string | null
  duration_seconds: number | null
  day_total_seconds: number | null
}
export type GardenState = {
  zone_id: string
  binding_ref: string
  server_time: string
  connection: 'unconfigured' | 'waiting' | 'fresh' | 'stale'
  last_seen_at: string | null
  snapshot_received_at: string | null
  snapshot: {
    observed_at: string | null
    time_quality: 'synced' | 'holdover' | 'unknown'
    output: 'on' | 'off' | 'unknown'
    active_session: Session | null
    applied_config_ref: string | null
    ready: boolean
    blocked_reason: string | null
  } | null
  config: ConfigView
  start_block_reason: string | null
  stop_available: boolean
  start_request: Command | null
  stop_request: Command | null
  next_schedule: Forecast
}
export type Preview = {
  preview_id: string
  duration_seconds: number
  expires_at: string
  context: { zone_id: string; binding_ref: string; config_ref: string; boot_id: string; control_epoch: number }
}
export type HistoryItem = {
  id: string
  kind: string
  source: Source | null
  result: string | null
  reason: string | null
  occurred_at: string | null
  received_at: string | null
  time_quality: string | null
  session_id: string | null
  request_id: string | null
  config_ref: string | null
  config_known: boolean
  duration_seconds: number | null
  planned_duration_seconds: number | null
  scheduled_at: string | null
}
export type HistoryView = { items: HistoryItem[]; next_cursor: string | null; coverage: 'partial' }
export type DailyPoint = {
  day: string
  schedule_seconds: number | null
  remote_seconds: number | null
  local_button_seconds: number | null
  coverage: 'unknown' | 'partial'
}
export type DailyView = { days: DailyPoint[]; forecast: Forecast }

const root = '/api/migarden'
function read<T>(path: string, signal?: AbortSignal) {
  return apiRequest<T>(root + path, { signal, cache: 'no-store' })
}
function mutate<T>(path: string, body: object, method = 'POST') {
  return apiRequest<T>(root + path, {
    method, body: JSON.stringify(body), headers: { 'X-MiGarden-CSRF': '1' }, cache: 'no-store',
  })
}
export const garden = {
  save: (bundle: Bundle, expected_config_ref: string | null) =>
    mutate<ConfigView>('/config', { ...bundle, expected_config_ref }, 'PUT'),
  preview: (duration_seconds: number) => mutate<Preview>('/start/preview', { duration_seconds }),
  confirm: (preview_id: string) => mutate<Command>('/start/confirm', { preview_id }),
  stop: () => mutate<Command>('/stop', {}),
  state: (signal?: AbortSignal) => read<GardenState>('/state', signal),
  daily: (days: 7 | 30, signal?: AbortSignal) => read<DailyView>('/daily?days=' + days, signal),
  history: (params: URLSearchParams, signal?: AbortSignal) =>
    read<HistoryView>('/history?' + params.toString(), signal),
}
export const gardenOptions = { retry: false, staleTime: 0, gcTime: 0, refetchIntervalInBackground: false }
export function useGardenState() {
  return useQuery({
    queryKey: ['migarden', 'state'],
    queryFn: ({ signal }) => garden.state(signal),
    ...gardenOptions,
    refetchInterval: query => {
      const data = query.state.data
      if (query.state.status === 'error') return 30_000
      if (data?.connection === 'unconfigured') return 30_000
      const waiting = ['pending', 'received', 'granted'].includes(data?.start_request?.status ?? '') ||
        ['stop_requested', 'stop_received', 'stop_unconfirmed'].includes(data?.stop_request?.status ?? '')
      return data?.snapshot?.active_session || waiting ? 5_000 : 15_000
    },
  })
}
