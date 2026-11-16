import { apiRequest } from '@/api'
import workletUrl from './mimi-pcm-worklet.js?url&no-inline'

export type VoicePhase = 'idle' | 'permission' | 'connecting' | 'listening' | 'speaking' | 'ending' | 'ended' | 'error'
export type VoiceState = {
  phase: VoicePhase
  muted: boolean
  startedAt: number | null
  caption: string
  captionRole: 'user' | 'assistant'
  notice: string | null
}
export const IDLE_VOICE: VoiceState = {
  phase: 'idle', muted: false, startedAt: null, caption: '', captionRole: 'user', notice: null,
}
type Ticket = { ticket: string; run_id: string; expires_in: number; max_seconds: number }
export type VoiceDependencies = {
  audioContext: () => AudioContext
  microphone: () => Promise<MediaStream>
  worklet: (context: AudioContext) => AudioWorkletNode
  ticket: (conversationId: string, generation: number, signal: AbortSignal) => Promise<Ticket>
  revoke: (conversationId: string, runId: string) => Promise<unknown>
  socket: (url: string) => WebSocket
}
const dependencies: VoiceDependencies = {
  audioContext: () => new AudioContext(),
  microphone: () => navigator.mediaDevices.getUserMedia({ audio: {
    channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true,
  }, video: false }),
  worklet: context => new AudioWorkletNode(context, 'mimi-pcm-capture', { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1] }),
  ticket: (id, generation, signal) => apiRequest(`/api/mimi/conversations/${id}/voice-ticket`, {
    method: 'POST', headers: { 'X-Mimi-CSRF': '1' }, signal,
    body: JSON.stringify({ expected_generation: generation }),
  }),
  revoke: (id, runId) => apiRequest(`/api/mimi/conversations/${id}/voice/${runId}/stop`, {
    method: 'POST', headers: { 'X-Mimi-CSRF': '1' }, body: '{}',
  }),
  socket: url => new WebSocket(url),
}

/** One explicit user action owns one session. No reconnect or text/provider handoff. */
export class MimiVoiceSession {
  private state: VoiceState = { ...IDLE_VOICE }
  private closed = false
  private ready = false
  private controller = new AbortController()
  private context?: AudioContext
  private stream?: MediaStream
  private capture?: AudioWorkletNode
  private microphoneSource?: MediaStreamAudioSourceNode
  private filter?: BiquadFilterNode
  private silent?: GainNode
  private socket?: WebSocket
  private runId?: string
  private ticketRequested = false
  private nextPlayback = 0
  private playing = new Set<AudioBufferSourceNode>()
  private timers = new Set<ReturnType<typeof setTimeout>>()
  private ending = false
  private reacquiring = false
  private conversationId: string
  private generation: number
  private changed: (state: VoiceState) => void
  private saved: () => void
  private deps: VoiceDependencies

  constructor(
    conversationId: string,
    generation: number,
    changed: (state: VoiceState) => void,
    saved: () => void,
    deps: VoiceDependencies = dependencies,
  ) {
    this.conversationId = conversationId
    this.generation = generation
    this.changed = changed
    this.saved = saved
    this.deps = deps
  }

  private update(change: Partial<VoiceState>) {
    this.state = { ...this.state, ...change }
    this.changed(this.state)
  }
  private later(work: () => void, ms: number) {
    const timer = setTimeout(() => { this.timers.delete(timer); work() }, ms)
    this.timers.add(timer)
    return timer
  }
  private ensureOpen() { if (this.closed) throw new DOMException('Stopped', 'AbortError') }

  private captureStream(stream: MediaStream) {
    const context = this.context!
    this.stream = stream
    for (const track of stream.getAudioTracks()) track.onended = () => this.fail('Micro đã ngắt. Bạn có thể tiếp tục bằng tin nhắn.')
    this.capture = this.deps.worklet(context)
    this.microphoneSource = context.createMediaStreamSource(stream)
    this.filter = context.createBiquadFilter()
    this.filter.type = 'lowpass'
    this.filter.frequency.value = 7400
    this.filter.Q.value = Math.SQRT1_2
    this.silent = context.createGain()
    this.silent.gain.value = 0
    this.microphoneSource.connect(this.filter).connect(this.capture).connect(this.silent).connect(context.destination)
    this.capture.port.onmessage = event => {
      if (this.closed || this.ending || !this.ready || this.state.muted || !(event.data instanceof ArrayBuffer)) return
      if (event.data.byteLength !== 1280 || !this.socket || this.socket.bufferedAmount > 64_000) {
        this.fail('Kết nối âm thanh bị chậm. Bạn có thể tiếp tục bằng tin nhắn.')
        return
      }
      try {
        if (this.socket.readyState === 1) this.socket.send(event.data)
      } catch { this.fail('Mất kết nối âm thanh. Bạn có thể tiếp tục bằng tin nhắn.') }
    }
  }

  private releaseMicrophone() {
    this.stream?.getTracks().forEach(track => { track.onended = null; track.stop() })
    if (this.capture) { this.capture.port.onmessage = null; this.capture.port.close(); this.capture.disconnect() }
    this.microphoneSource?.disconnect()
    this.filter?.disconnect()
    this.silent?.disconnect()
    this.capture = this.microphoneSource = this.filter = this.silent = this.stream = undefined
  }

  async start() {
    if (this.state.phase !== 'idle' || this.closed) return
    this.update({ phase: 'permission' })
    const mediaTimer = this.later(() => this.fail('Chưa mở được micro. Bạn có thể tiếp tục bằng tin nhắn.'), 30_000)
    try {
      // Created AND resumed in the click's synchronous stack, before permission
      // awaits, so Safari receives a real user audio activation.
      this.context = this.deps.audioContext()
      const resumed = this.context.resume()
      // Handle both promises immediately; a refused AudioContext cannot leak a
      // late permission grant's MediaStream after stop/unmount/auth purge.
      const media = this.deps.microphone().then(stream => {
        if (this.closed) stream.getTracks().forEach(track => track.stop())
        else this.stream = stream
        return stream
      })
      await Promise.all([resumed, media])
      clearTimeout(mediaTimer)
      this.timers.delete(mediaTimer)
      this.ensureOpen()
      const context = this.context
      if (!context.audioWorklet) throw new Error('unsupported_audio')
      await context.audioWorklet.addModule(workletUrl)
      this.ensureOpen()
      this.captureStream(this.stream!)
      this.update({ phase: 'connecting' })
      this.ticketRequested = true
      const ticket = await this.deps.ticket(this.conversationId, this.generation, this.controller.signal)
      if (this.closed) {
        void this.deps.revoke(this.conversationId, ticket.run_id).catch(() => {}).finally(this.saved)
        return
      }
      this.runId = ticket.run_id
      const url = new URL(`/api/mimi/conversations/${this.conversationId}/voice/${ticket.run_id}`, window.location.href)
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
      const socket = this.deps.socket(url.href)
      this.socket = socket
      socket.binaryType = 'arraybuffer'
      const connectionTimer = this.later(() => this.fail('Chưa kết nối được giọng nói. Bạn có thể thử lại hoặc nhắn Mimi.'), 15_000)
      socket.onopen = () => {
        if (this.closed) { socket.close(); return }
        try { socket.send(JSON.stringify({ type: 'ticket', ticket: ticket.ticket })) }
        catch { this.fail('Chưa kết nối được giọng nói. Bạn có thể tiếp tục bằng tin nhắn.') }
        finally { ticket.ticket = '' }
      }
      socket.onmessage = event => {
        if (this.closed) return
        if (event.data instanceof ArrayBuffer) {
          if (this.ending) return
          try { this.play(event.data) } catch { this.fail('Không phát được âm thanh. Bạn có thể tiếp tục bằng tin nhắn.') }
          return
        }
        try {
          if (typeof event.data !== 'string' || event.data.length > 32_768) throw new Error('invalid_frame')
          const message = JSON.parse(event.data)
          if (this.ending && message.type !== 'ended') return
          if (message.type === 'ready') {
            if (this.ready || message.run_id !== this.runId) throw new Error('invalid_session')
            clearTimeout(connectionTimer)
            this.timers.delete(connectionTimer)
            this.ready = true
            this.update({ phase: 'listening', startedAt: Date.now() })
            this.later(() => this.stop('Phiên giọng nói đã hết thời lượng. Bạn có thể bắt đầu phiên mới.'), ticket.max_seconds * 1000)
          } else if (message.type === 'interrupted') {
            this.clearPlayback()
            this.update({ phase: 'listening', caption: '' })
          } else if (message.type === 'transcript' && ['user', 'assistant'].includes(message.role) && typeof message.text === 'string' && message.text.length <= 16_384) {
            this.update({ caption: message.text, captionRole: message.role })
          } else if (message.type === 'transcript_saved') {
            this.update({ caption: '' })
            this.saved()
          } else if (message.type === 'turn_complete') {
            // Audio may still be scheduled. Only source.onended means playback ended.
            if (!this.playing.size) this.update({ phase: 'listening' })
          } else if (message.type === 'ended') {
            this.finish(message.reason === 'voice_stopped' ? null : 'Phiên giọng nói đã kết thúc. Bản chép lời có thể chưa đầy đủ; bạn vẫn có thể nhắn Mimi.')
          } else if (message.type !== 'muted') {
            throw new Error('invalid_event')
          }
        } catch { this.fail('Kết nối giọng nói không hợp lệ. Bạn có thể tiếp tục bằng tin nhắn.') }
      }
      socket.onerror = () => this.fail('Mất kết nối giọng nói. Bản nháp được giữ; bạn có thể nhắn Mimi.')
      socket.onclose = () => {
        if (!this.closed && !this.ending) this.fail('Phiên giọng nói bị ngắt. Bản chép lời có thể chưa đầy đủ; bạn có thể nhắn Mimi.')
        else if (this.ending) this.finish(null)
      }
    } catch (error) {
      if (this.closed) return
      const denied = error instanceof DOMException && ['NotAllowedError', 'PermissionDeniedError'].includes(error.name)
      this.fail(denied
        ? 'Chưa được phép dùng micro. Cho phép micro khi sẵn sàng, hoặc tiếp tục nhắn Mimi.'
        : 'Chưa mở được giọng nói trên thiết bị này. Bản nháp được giữ; bạn có thể nhắn Mimi.')
    }
  }

  private play(data: ArrayBuffer) {
    const context = this.context
    if (!context || !this.ready || !data.byteLength || data.byteLength % 2 || data.byteLength > 262_144) throw new Error('invalid_pcm')
    const begin = Math.max(context.currentTime + 0.02, this.nextPlayback)
    const duration = data.byteLength / 48_000
    if (begin + duration - context.currentTime > 15) throw new Error('playback_queue_limit')
    const buffer = context.createBuffer(1, data.byteLength / 2, 24_000)
    const samples = buffer.getChannelData(0)
    const view = new DataView(data)
    for (let i = 0; i < samples.length; i++) samples[i] = view.getInt16(i * 2, true) / 32768
    const source = context.createBufferSource()
    source.buffer = buffer
    source.connect(context.destination)
    this.playing.add(source)
    source.onended = () => {
      source.disconnect()
      this.playing.delete(source)
      if (!this.closed && !this.playing.size) this.update({ phase: 'listening' })
    }
    source.start(begin)
    this.nextPlayback = begin + duration
    this.update({ phase: 'speaking' })
  }
  private clearPlayback() {
    for (const source of this.playing) {
      source.onended = null
      try { source.stop(); source.disconnect() } catch { /* Already ended. */ }
    }
    this.playing.clear()
    this.nextPlayback = 0
  }
  mute() {
    if (this.closed || this.ending || !this.ready || this.reacquiring) return
    const socket = this.socket
    if (!socket || socket.readyState !== 1) return
    if (!this.state.muted) {
      this.releaseMicrophone()
      this.update({ muted: true })
      try { socket.send(JSON.stringify({ type: 'mute', muted: true })) }
      catch { this.fail('Mất kết nối âm thanh. Bạn có thể tiếp tục bằng tin nhắn.') }
      return
    }
    this.reacquiring = true
    void this.deps.microphone().then(stream => {
      if (this.closed || this.ending) { stream.getTracks().forEach(track => track.stop()); return }
      this.captureStream(stream)
      socket.send(JSON.stringify({ type: 'mute', muted: false }))
      this.update({ muted: false })
    }).catch(() => this.fail('Không bật lại được micro. Bạn có thể tiếp tục bằng tin nhắn.'))
      .finally(() => { this.reacquiring = false })
  }
  private fail(notice: string) {
    if (this.closed) return
    this.dispose(true)
    this.update({ phase: 'error', notice, caption: '' })
  }
  stop(notice: string | null = null) {
    if (this.closed || this.ending) return
    if (this.ready && this.socket?.readyState === 1) {
      this.ending = true
      this.releaseAudio()
      this.update({ phase: 'ending', notice, caption: '' })
      try {
        this.socket.send(JSON.stringify({ type: 'stop' }))
        this.later(() => this.finish(notice, true), 5_000)
      } catch { this.finish(notice, true) }
    } else this.finish(notice, true)
  }
  cancel() { this.finish(null, true) }
  private finish(notice: string | null, revoke = false) {
    if (this.closed) return
    this.dispose(revoke)
    this.update({ phase: 'ended', notice, caption: '' })
  }
  private releaseAudio() {
    this.clearPlayback()
    this.releaseMicrophone()
    if (this.context && this.context.state !== 'closed') void this.context.close().catch(() => {})
    this.context = undefined
  }
  private dispose(revoke: boolean) {
    if (this.closed) return
    this.closed = true
    this.controller.abort()
    for (const timer of this.timers) clearTimeout(timer)
    this.timers.clear()
    this.releaseAudio()
    if (this.socket) {
      this.socket.onmessage = this.socket.onerror = this.socket.onclose = null
      try { this.socket.close(1000) } catch { /* CONNECTING will close in onopen. */ }
    }
    if (revoke && this.runId) void this.deps.revoke(this.conversationId, this.runId).catch(() => {}).finally(this.saved)
    else if (this.ticketRequested) this.saved()
    this.ready = false
  }
}
