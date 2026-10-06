import type { MimiModelProfile } from './mimi-api'

const INPUT_PRESETS = [100_000]

export function availableInputPresets(profile: MimiModelProfile | undefined) {
  if (!profile) return []
  const maximum = profile.context_limit
  return INPUT_PRESETS.filter((tokens) => tokens <= maximum)
}

export function effortOptions(profile: MimiModelProfile | undefined) {
  if (!profile || profile.supported_efforts.length === 0) return ['default']
  return profile.supported_efforts
}
