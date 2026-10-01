import { expect, test } from 'vitest'

import { availableInputPresets, effortOptions } from './mimi-configuration.ts'
import type { MimiModelProfile } from './mimi-api.ts'

function profile(overrides: Partial<MimiModelProfile> = {}): MimiModelProfile {
  return {
    id: 'profile-1',
    label: 'Model',
    model: 'model',
    provider: 'local',
    quantization: 'Q4',
    supported_efforts: ['low', 'high'],
    context_limit: 232_000,
    output_reserve: 32_000,
    available: true,
    unavailable_reason: null,
    ...overrides,
  }
}

test('input presets stay within the model context after reserving output tokens', () => {
  expect(availableInputPresets(profile())).toEqual([32_000, 100_000, 200_000])
  expect(availableInputPresets(profile({ context_limit: 132_000 }))).toEqual([32_000, 100_000])
  expect(availableInputPresets(profile({ context_limit: 63_999 }))).toEqual([])
})

test('profiles without advertised effort levels use the provider default', () => {
  expect(effortOptions(profile({ supported_efforts: [] }))).toEqual(['default'])
  expect(effortOptions(profile({ supported_efforts: ['medium'] }))).toEqual(['medium'])
})
