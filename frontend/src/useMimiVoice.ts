import { useCallback, useEffect, useRef, useState } from 'react'
import type { QueryClient } from '@tanstack/react-query'
import { isMimiSessionCurrent, onMimiSessionPurge } from './mimi-session-boundary'
import { IDLE_VOICE, MimiVoiceSession } from './mimi-voice'

export function useMimiVoice(client: QueryClient, epoch: number, conversationId: string | undefined, allowed: boolean) {
  const [view, setView] = useState({ conversationId, state: IDLE_VOICE })
  const session = useRef<MimiVoiceSession | null>(null)
  const cancel = useCallback(() => {
    const previous = session.current
    previous?.cancel()
    session.current = null
  }, [])
  useEffect(() => onMimiSessionPurge(client, () => { cancel(); setView({ conversationId, state: IDLE_VOICE }) }), [client, cancel, conversationId])
  useEffect(() => {
    const disconnected = () => session.current?.stop('Mất mạng. Bản nháp được giữ; bạn có thể nhắn Mimi khi có mạng.')
    window.addEventListener('offline', disconnected)
    window.addEventListener('pagehide', cancel)
    return () => { window.removeEventListener('offline', disconnected); window.removeEventListener('pagehide', cancel); cancel() }
  }, [cancel, conversationId, allowed])
  const start = (generation: number) => {
    if (!allowed || !conversationId || !isMimiSessionCurrent(client, epoch)) return
    if (session.current) return
    const voice: MimiVoiceSession = new MimiVoiceSession(conversationId, generation, next => {
      if (session.current !== voice || !isMimiSessionCurrent(client, epoch)) return
      setView({ conversationId, state: next })
      if (next.phase === 'ended' || next.phase === 'error') session.current = null
    }, () => {
      if (!isMimiSessionCurrent(client, epoch)) return
      void client.invalidateQueries({ queryKey: ['mimi', 'conversation', conversationId] })
      void client.invalidateQueries({ queryKey: ['mimi', 'current'] })
      void client.invalidateQueries({ queryKey: ['mimi', 'conversations'] })
    })
    session.current = voice
    void voice.start()
  }
  const state = allowed && conversationId === view.conversationId ? view.state : IDLE_VOICE
  return {
    state,
    active: ['permission', 'connecting', 'listening', 'speaking', 'ending'].includes(state.phase),
    start,
    mute: () => session.current?.mute(),
    stop: () => session.current?.stop(),
  }
}
