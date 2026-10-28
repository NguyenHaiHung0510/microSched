import type { MimiModelProfile } from './mimi-api'

export function availableInputPresets(profile: MimiModelProfile | undefined) {
  if (!profile) return []
  const trigger = profile.compaction_trigger_tokens ?? 272_000
  return trigger + profile.output_reserve <= profile.context_limit ? [trigger] : []
}

export function effortOptions(profile: MimiModelProfile | undefined) {
  if (!profile || profile.supported_efforts.length === 0) return ['default']
  return profile.supported_efforts
}
