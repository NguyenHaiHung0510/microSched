import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { QueryClient } from '@tanstack/react-query'
import { CALENDAR_TASKS_KEY } from './calendar-queries'
import { isMimiSessionCurrent, onMimiSessionPurge } from './mimi-session-boundary'
import { IDLE_VOICE, MimiVoiceSession, type VoiceActionStatus } from './mimi-voice'

function conversationQueries(conversationId: string) {
  return [
    { queryKey: ['mimi', 'conversation', conversationId], exact: true },
    { queryKey: ['mimi', 'current'], exact: true },
    { queryKey: ['mimi', 'conversations'] },
  ]
}

export async function refreshMimiVoiceAction(client: QueryClient, epoch: number, conversationId: string, status: VoiceActionStatus) {
  if (!isMimiSessionCurrent(client, epoch)) return
  const queries = conversationQueries(conversationId)
  if (status === 'applied' || status === 'undone') {
    queries.push({ queryKey: [...CALENDAR_TASKS_KEY] }, { queryKey: ['tasks'] })
  }
  // A cold read started before the action may otherwise publish stale data.
  await Promise.all(queries.map(filter => client.cancelQueries(filter)))
  if (!isMimiSessionCurrent(client, epoch)) return
  await Promise.all(queries.map(filter => client.invalidateQueries(filter)))
}

export function useMimiVoice(client: QueryClient, epoch: number, conversationId: string | undefined, allowed: boolean, v2 = false) {
  const [view, setView] = useState({ conversationId, v2, state: IDLE_VOICE })
  const session = useRef<MimiVoiceSession | null>(null)
  const cancel = useCallback(() => {
    const previous = session.current
    previous?.cancel()
    session.current = null
  }, [])
  useLayoutEffect(() => onMimiSessionPurge(client, () => { cancel(); setView({ conversationId, v2, state: IDLE_VOICE }) }), [client, cancel, conversationId, v2])
  // Closing side-chat or changing its conversation releases audio during unmount,
  // without touching a text run or relying on blur/visibility changes.
  useLayoutEffect(() => cancel, [cancel, conversationId, allowed, v2, epoch])
  useEffect(() => {
    const disconnected = () => session.current?.stop('Mất mạng. Bản nháp được giữ; bạn có thể nhắn Mimi khi có mạng.')
    window.addEventListener('offline', disconnected)
    window.addEventListener('pagehide', cancel)
    return () => { window.removeEventListener('offline', disconnected); window.removeEventListener('pagehide', cancel) }
  }, [cancel])
  const start = (generation: number) => {
    if (!allowed || !conversationId || !isMimiSessionCurrent(client, epoch)) return
    if (session.current) return
    const voice: MimiVoiceSession = new MimiVoiceSession(conversationId, generation, next => {
      if (session.current !== voice || !isMimiSessionCurrent(client, epoch)) return
      setView({ conversationId, v2, state: next })
      if (next.phase === 'ended' || next.phase === 'error') session.current = null
    }, () => {
      if (!isMimiSessionCurrent(client, epoch)) return
      for (const filter of conversationQueries(conversationId)) void client.invalidateQueries(filter)
    }, undefined, {
      v2,
      actionUpdated: status => { void refreshMimiVoiceAction(client, epoch, conversationId, status) },
    })
    session.current = voice
    void voice.start()
  }
  const state = allowed && v2 === view.v2 && conversationId === view.conversationId ? view.state : IDLE_VOICE
  return {
    state,
    active: ['permission', 'connecting', 'listening', 'speaking', 'reconnecting', 'ending'].includes(state.phase),
    start,
    mute: () => session.current?.mute(),
    stop: () => session.current?.stop(),
  }
}
