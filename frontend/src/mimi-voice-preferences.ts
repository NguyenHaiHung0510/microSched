import type { QueryClient } from '@tanstack/react-query'
import type { MimiVoicePreferences } from './mimi-api'
import { isMimiSessionCurrent } from './mimi-session-boundary'

export const MIMI_VOICE_PREFERENCES_KEY = ['mimi', 'voice-preferences'] as const

export async function publishMimiVoicePreferences(client: QueryClient, epoch: number, confirmed: MimiVoicePreferences) {
  if (!isMimiSessionCurrent(client, epoch)) return
  // Fence GETs started before this PATCH settled, including focus revalidation.
  await client.cancelQueries({ queryKey: MIMI_VOICE_PREFERENCES_KEY, exact: true })
  if (isMimiSessionCurrent(client, epoch)) client.setQueryData(MIMI_VOICE_PREFERENCES_KEY, confirmed)
}
