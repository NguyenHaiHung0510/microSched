import type { QueryClient, QueryKey } from '@tanstack/react-query'
import type { GardenState } from './api'
import { humanActive } from '@/human-activity'

export const OUTPUT_FRESH_MS = 15_000
export type ConfirmedOutput = { output: 'on' | 'off'; receivedAt: string }
// Local cache metadata, never sent to the server or persisted. It follows the
// authenticated query identity and is preserved by command/config patches.
export type GardenReading = GardenState & {
  readClock: { serverTime: number; receivedAt: number }
  confirmedOutput: ConfirmedOutput | null
}
export function sameGarden(a: GardenState, b: GardenState) {
  return a.zone_id === b.zone_id && a.binding_ref === b.binding_ref
}
export function gardenServerNow(state: GardenState, receivedAt: number, now: number) {
  const clock = (state as Partial<GardenReading>).readClock
  return (clock?.serverTime ?? Date.parse(state.server_time)) + Math.max(0, now - (clock?.receivedAt ?? receivedAt))
}
export function acceptGardenReading(previous: GardenReading | undefined, state: GardenState, now: number): GardenReading {
  const matching = previous && sameGarden(previous, state) ? previous : undefined
  // A late/older response cannot roll the accepted report back. Command/config
  // writes also cancel the pre-write GET before patching this same cache entry.
  if (matching && Date.parse(state.server_time) < Date.parse(matching.server_time)) return matching
  if (matching?.snapshot_received_at && state.snapshot_received_at && Date.parse(state.snapshot_received_at) < Date.parse(matching.snapshot_received_at)) {
    state = { ...state, snapshot: matching.snapshot, snapshot_received_at: matching.snapshot_received_at }
  }
  if (matching) {
    const before = (a: string | null, b: string | null) => !!b && (!a || Date.parse(a) < Date.parse(b))
    if (before(state.config.desired_saved_at, matching.config.desired_saved_at) || before(state.config.applied_confirmed_at, matching.config.applied_confirmed_at)) {
      state = { ...state, config: matching.config }
    }
    for (const key of ['start_request', 'stop_request'] as const) {
      if (before(state[key]?.confirmed_at ?? null, matching[key]?.confirmed_at ?? null)) state = { ...state, [key]: matching[key] }
    }
  }
  const serverTime = Math.max(Date.parse(state.server_time), matching ? gardenServerNow(matching, now, now) : -Infinity)
  const output = state.snapshot?.output
  const confirmedOutput = state.snapshot_received_at && (output === 'on' || output === 'off')
    ? { output, receivedAt: state.snapshot_received_at } : matching?.confirmedOutput ?? null
  return { ...state, readClock: { serverTime, receivedAt: now }, confirmedOutput }
}
const changed = (a: unknown, b: unknown) => JSON.stringify(a) !== JSON.stringify(b)
export function gardenDependencyChanges(previous: GardenState | undefined, next: GardenState) {
  const changes = new Set<string>()
  if (!previous || !sameGarden(previous, next)) return changes
  const { schedule_projection: previousProjection, ...previousConfig } = previous.config
  const { schedule_projection: nextProjection, ...nextConfig } = next.config
  const config = changed(previousConfig, nextConfig)
  const phase = (state: GardenState) => {
    const snapshot = state.snapshot, session = snapshot?.active_session
    return [snapshot?.output, session?.session_id, session?.request_id, session?.trigger_source, session?.started_at, session?.duration_seconds, session?.config_ref]
  }
  // Heartbeat receipt, observed_at and elapsed are deliberately excluded.
  const report = changed(phase(previous), phase(next))
  const command = changed([previous.start_request, previous.stop_request], [next.start_request, next.stop_request])
  if (config || report || command) changes.add('history')
  if (config || report || changed(previous.next_schedule, next.next_schedule) || changed(previousProjection, nextProjection)) changes.add('daily')
  if (config) { changes.add('versions'); changes.add('version') }
  if (changed(previous.health, next.health)) changes.add('health')
  return changes
}
export function invalidateGardenDependencies(client: QueryClient, previous: GardenState | undefined, next: GardenState) {
  const changes = gardenDependencyChanges(previous, next)
  if (!changes.size) return
  void client.invalidateQueries({
    predicate: query => query.queryKey[0] === 'migarden' && changes.has(String(query.queryKey[1])),
    refetchType: humanActive() ? 'active' : 'none',
  }, { cancelRefetch: false })
}
export function refreshGarden(client: QueryClient) {
  if (!humanActive()) return
  void client.refetchQueries({ type: 'active', predicate: query => query.queryKey[0] === 'migarden' }, { cancelRefetch: false })
}
export async function patchGardenState(client: QueryClient, key: QueryKey, patch: Partial<Pick<GardenState, 'config' | 'start_request' | 'stop_request'>>) {
  await client.cancelQueries({ queryKey: key, exact: true })
  const previous = client.getQueryData<GardenReading>(key)
  if (previous) {
    const next = { ...previous, ...patch }
    client.setQueryData(key, next, { updatedAt: client.getQueryState(key)?.dataUpdatedAt })
    invalidateGardenDependencies(client, previous, next)
  }
  // A post-mutation read cannot be an older, already in-flight GET.
  void client.refetchQueries({ queryKey: key, exact: true, type: 'active' }, { cancelRefetch: false })
}
