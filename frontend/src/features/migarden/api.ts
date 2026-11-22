import { apiRequest } from '@/api'
import { useEffect, useSyncExternalStore } from 'react'
import { useQuery } from '@tanstack/react-query'
import { gardenPresenceHeaders, listenGardenActivity } from './presence'
import { humanActive, useHumanActive } from '@/human-activity'

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
  schedule_projection?: ScheduleProjection
}
export type ScheduleProjection = { saved: Forecast; last_confirmed: Forecast; application_status: ConfigView['application_status']; possible_previous_run: boolean }
export type Health = { sample_id: string; received_at: string; sample: { build_id: string; boot_id: string; sampled_at: string | null; time_quality: string; uptime_seconds: number; reset_reason: number | null; free_heap: number; minimum_heap: number; wifi_phase: string; sync_status: string; pending_reports: number; evidence_gaps: number } }
export type Version = { config_ref: string; saved_at: string; bundle: Config; is_saved?: boolean; is_last_confirmed?: boolean }
export type VersionDetail = Version & { previous_ref: string | null; previous_bundle: Config | null; schedule_changed: boolean; last_confirmed_ref: string | null; evidence: { event_id: string; kind: string; boot_id: string; sequence: number; applied_at: string | null; occurred_at: string | null; received_at: string; time_quality: string; reason: string | null }[] }
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
  health?: Health | null
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
export type TimelineItem = HistoryItem & {
  started_at: string | null
  ended_at: string | null
  evidence: HistoryItem[]
}
export type HistoryTimeline = {
  items: TimelineItem[]
  next_cursor: string | null
  coverage: 'partial'
  totals: { recorded_seconds: number | null; schedule_seconds: number | null; remote_seconds: number | null; local_button_seconds: number | null } | null
}
export type DailyPoint = {
  day: string
  schedule_seconds: number | null
  remote_seconds: number | null
  local_button_seconds: number | null
  coverage: 'unknown' | 'partial'
}
export type DailyView = { days: DailyPoint[]; forecast: Forecast; schedule_projection?: ScheduleProjection }

const root = '/api/migarden'
export const gardenConfigMutation = ['migarden', 'save-config'] as const
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
  state: (signal?: AbortSignal) => apiRequest<GardenState>(root + '/state', {
    signal, cache: 'no-store',
    headers: gardenPresenceHeaders(),
  }),
  daily: (days: 7 | 30, signal?: AbortSignal) => read<DailyView>('/daily?days=' + days, signal),
  history: (params: URLSearchParams, signal?: AbortSignal) =>
    read<HistoryView>('/history?' + params.toString(), signal),
  timeline: (params: URLSearchParams, signal?: AbortSignal) =>
    read<HistoryTimeline>('/history?' + params.toString(), signal),
  versions: (params: URLSearchParams, signal?: AbortSignal) => read<{ items: Version[]; next_cursor: string | null }>('/config/versions?' + params, signal),
  version: (ref: string, signal?: AbortSignal) => read<VersionDetail>('/config/versions/' + encodeURIComponent(ref), signal),
  health: (params: URLSearchParams, signal?: AbortSignal) => read<{ items: Health[]; boots: { boot_id: string; first_seen_at: string }[]; next_cursor: string | null }>('/health?' + params, signal),
}
export const gardenOptions = { retry: false, staleTime: 0, gcTime: 0, refetchIntervalInBackground: false }
function subscribeVisibility(listener: () => void) {
  window.addEventListener('visibilitychange', listener, true)
  return () => window.removeEventListener('visibilitychange', listener, true)
}
export function gardenStateInterval(data: GardenState | undefined, status: string, visible: boolean) {
  if (!visible || !humanActive()) return false
  if (status === 'error' || data?.connection === 'unconfigured') return 30_000
  return 1_000
}
export function useGardenState(controlPage = true) {
  useEffect(listenGardenActivity, [])
  const visible = useSyncExternalStore(subscribeVisibility,
    () => document.visibilityState === 'visible', () => false)
  const active = useHumanActive()
  return useQuery({
    queryKey: ['migarden', 'state'],
    queryFn: ({ signal }) => garden.state(signal),
    ...gardenOptions,
    enabled: visible && active,
    refetchInterval: query => controlPage
      ? gardenStateInterval(query.state.data, query.state.status, visible)
      : visible && active ? 30_000 : false,
  })
}
