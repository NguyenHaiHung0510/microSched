import { useEffect, useRef, useState } from 'react'
import { Mic, MicOff, PhoneOff } from 'lucide-react'
import { MimiAvatar } from '@/components/brand'
import { Button } from '@/components/ui/button'
import type { VoiceState } from './mimi-voice'

export function MimiVoiceDock({ state, mute, stop, v2 = false }: { state: VoiceState; mute: () => void; stop: () => void; v2?: boolean }) {
  const [now, setNow] = useState(0)
  const stopButton = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (document.activeElement === document.body) stopButton.current?.focus({ preventScroll: true })
  }, [])
  useEffect(() => {
    if (state.startedAt === null) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [state.startedAt])
  const seconds = state.startedAt === null ? 0 : Math.max(0, Math.floor((now - state.startedAt) / 1000))
  const clock = `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`
  const starting = state.phase === 'permission' || state.phase === 'connecting' || state.phase === 'reconnecting' || state.phase === 'ending'
  const label = state.phase === 'permission' ? 'Đang mở micro…' : state.phase === 'connecting' ? 'Đang kết nối…'
    : state.phase === 'reconnecting' ? 'Đang nối lại…'
      : state.phase === 'ending' ? 'Đang kết thúc…' : state.phase === 'speaking' ? 'Mimi đang nói' : state.muted ? 'Micro đang tắt' : 'Đang nghe bạn'
  const MicIcon = state.muted ? Mic : MicOff
  return <section aria-label="Giọng nói Mimi" aria-describedby="mimi-voice-scope" className="mimi-voice" data-testid="mimi-voice-dock">
    <div className="mimi-voice-live">
      <span className="mimi-voice-ring" aria-hidden="true"><MimiAvatar size="md" /></span>
      <div className="min-w-0">
        <p className="text-sm font-extrabold" role="status">{label}</p>
        <p className="mimi-voice-clock text-sm tabular-nums" aria-label={`Thời lượng ${Math.floor(seconds / 60)} phút ${seconds % 60} giây`}>{clock}</p>
      </div>
      <span className="mimi-voice-level" data-moving={!starting && (!state.muted || state.phase === 'speaking')} aria-hidden="true"><i /><i /><i /><i /></span>
    </div>
    <div className="mimi-voice-controls">
      <Button type="button" variant="outline" onClick={mute} disabled={v2 ? state.phase === 'ending' : starting} data-testid="mimi-voice-mute"><MicIcon aria-hidden="true" />{state.muted ? 'Bật mic' : 'Tắt mic'}</Button>
      <Button ref={stopButton} type="button" onClick={stop} disabled={state.phase === 'ending'} data-testid="mimi-voice-stop"><PhoneOff aria-hidden="true" />Kết thúc</Button>
    </div>
    <span id="mimi-voice-scope" className="mimi-voice-scope">{v2 ? 'Giọng nói · Tắt mic sẽ kết thúc cuộc gọi' : 'Chỉ đọc lịch · dùng tin nhắn để chỉnh sửa'}</span>
    {state.caption ? <p className="mimi-voice-caption"><strong>{state.captionRole === 'assistant' ? 'Mimi: ' : 'Bạn: '}</strong>{state.caption}</p> : null}
  </section>
}
