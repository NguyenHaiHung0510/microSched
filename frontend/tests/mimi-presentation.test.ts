import { expect, test } from 'vitest'

import { mimiRunIsResumable } from '../src/mimi-presentation.ts'

test('server resumable flag is authoritative for pause and recovery states', () => {
  expect(mimiRunIsResumable({ state: 'halted', provider_outcome: 'succeeded', resumable: true })).toBe(true)
  expect(mimiRunIsResumable({ state: 'retryable', provider_outcome: 'succeeded', resumable: false })).toBe(false)
})

test('legacy resume fallback is limited to known resumable states', () => {
  expect(mimiRunIsResumable({ state: 'retryable', provider_outcome: 'failed' })).toBe(true)
  expect(mimiRunIsResumable({ state: 'owner_paused', provider_outcome: 'succeeded' })).toBe(false)
  expect(mimiRunIsResumable({ state: 'outcome_unknown', provider_outcome: 'unknown' })).toBe(false)
})
