import { apiRequest } from '@/api'
import workletUrl from './mimi-pcm-worklet.js?url&no-inline'

export type VoicePhase = 'idle' | 'permission' | 'connecting' | 'listening' | 'speaking' | 'reconnecting' | 'ending' | 'ended' | 'error'
export type VoiceActionStatus = 'preview' | 'applied' | 'undone'
export type VoiceState = {
  phase: VoicePhase
  muted: boolean
  startedAt: number | null
  caption: string
  captionRole: 'user' | 'assistant'
  notice: string | null
  actionStatus: VoiceActionStatus | null
}
export const IDLE_VOICE: VoiceState = {
  phase: 'idle', muted: false, startedAt: null, caption: '', captionRole: 'user', notice: null, actionStatus: null,
}
const CAPTURE_FRAME_BYTES = 1280
const CAPTURE_LOSS_MS = 5_000
const MAX_CALL_MS = 90 * 60_000
const SEND_BUFFER_BYTES = 64_000
const OUTPUT_BYTES_PER_SECOND = 48_000
const MAX_AUDIO_FRAME_BYTES = 262_144
const V2_PLAYBACK_BUDGET = 30 * OUTPUT_BYTES_PER_SECOND
const V2_PLAYBACK_LEAD = 2
const V2_PLAYBACK_CHUNK = OUTPUT_BYTES_PER_SECOND / 2
const V2_MAX_PLAYING_NODES = 64
const V2_MAX_QUEUED_FRAMES = 1536
const CHECK_SAVED_RESULT = 'Hãy kiểm tra Task hoặc kết quả đã lưu trước khi gửi lại yêu cầu.'
const CALL_LIMIT = 'Đã hết thời lượng cuộc gọi. Bạn có thể bắt đầu cuộc gọi mới.'
const CAPTURE_LOST = 'Micro đã ngắt. Bạn có thể tiếp tục bằng tin nhắn.'
const PLAYBACK_FAILED = 'Không phát được âm thanh. Bạn có thể tiếp tục bằng tin nhắn.'
type Ticket = { ticket: string; run_id: string; expires_in: number; max_seconds: number }
type VoiceOptions = { v2?: boolean; actionUpdated?: (status: VoiceActionStatus) => void }
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

/** One explicit user action owns the mic and app socket. V2 provider resumption
 * stays behind that socket; the client never reopens a dropped call. */
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
  private playbackQueue: { data: ArrayBuffer; offset: number }[] = []
  private playbackBytes = 0
  private dropOutputUntilBoundary = false
  private turnActive = false
  private interruptedBeforeResume = false
  private captureResetSequence = 0
  private pendingCaptureReset: number | null = null
  private captureTimer?: ReturnType<typeof setTimeout>
  private lastCaptureAt = 0
  private micStartedMonotonic = 0
  private callLimitMs = MAX_CALL_MS
  private timers = new Set<ReturnType<typeof setTimeout>>()
  private ending = false
  private reacquiring = false
  private conversationId: string
  private generation: number
  private changed: (state: VoiceState) => void
  private saved: (reconcileUnknown?: true) => void
  private deps: VoiceDependencies
  private options: VoiceOptions

  constructor(
    conversationId: string,
    generation: number,
    changed: (state: VoiceState) => void,
    saved: (reconcileUnknown?: true) => void,
    deps: VoiceDependencies = dependencies,
    options: VoiceOptions = {},
  ) {
    this.conversationId = conversationId
    this.generation = generation
    this.changed = changed
    this.saved = saved
    this.deps = deps
    this.options = options
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

  private remainingCallTime() {
    return this.callLimitMs - Math.max(
      Date.now() - this.state.startedAt!,
      performance.now() - this.micStartedMonotonic,
    )
  }

  private checkDeadline() {
    if (!this.options.v2 || this.state.startedAt === null || this.remainingCallTime() > 0) return false
    this.stop(CALL_LIMIT)
    return true
  }

  private checkCapture() {
    if (!this.capture || this.closed || this.ending) return
    const remaining = CAPTURE_LOSS_MS - (performance.now() - this.lastCaptureAt)
    if (remaining <= 0) this.fail(CAPTURE_LOST)
    else this.captureTimer = this.later(() => this.checkCapture(), remaining)
  }

  private disconnectNotice(fallback: string) {
    return this.options.v2 && (this.turnActive || this.playing.size || this.playbackBytes || this.interruptedBeforeResume)
      ? 'Kết nối đã ngắt giữa lượt.'
      : fallback
  }

  private checkSavedNotice(notice: string) {
    return this.options.v2 && this.ready ? `${notice} ${CHECK_SAVED_RESULT}` : notice
  }

  private captureStream(stream: MediaStream) {
    const context = this.context!
    this.stream = stream
    const tracks = stream.getAudioTracks()
    if (this.options.v2 && !tracks.some(track => track.readyState === 'live' && track.enabled && !track.muted)) {
      this.fail(CAPTURE_LOST)
      return
    }
    const capture = this.capture = this.deps.worklet(context)
    const lost = () => { if (this.capture === capture) this.fail(CAPTURE_LOST) }
    for (const track of tracks) {
      track.onended = lost
      if (this.options.v2) track.onmute = lost
    }
    if (this.options.v2) {
      capture.onprocessorerror = lost
      capture.port.onmessageerror = lost
      this.lastCaptureAt = performance.now()
      this.checkCapture()
    }
    this.microphoneSource = context.createMediaStreamSource(stream)
    this.filter = context.createBiquadFilter()
    this.filter.type = 'lowpass'
    this.filter.frequency.value = 7400
    this.filter.Q.value = Math.SQRT1_2
    this.silent = context.createGain()
    this.silent.gain.value = 0
    this.microphoneSource.connect(this.filter).connect(this.capture).connect(this.silent).connect(context.destination)
    capture.port.onmessage = event => {
      if (this.closed || this.ending || this.capture !== capture) return
      if (this.pendingCaptureReset !== null && event.data?.captureReset === this.pendingCaptureReset) {
        this.pendingCaptureReset = null
        return
      }
      if (!(event.data instanceof ArrayBuffer)) return
      if (this.options.v2 && event.data.byteLength === CAPTURE_FRAME_BYTES) {
        // Silence still produces PCM frames. A missing input channel produces none.
        this.lastCaptureAt = performance.now()
        if (this.checkDeadline()) return
      }
      if (!this.ready || this.state.muted || this.state.phase === 'reconnecting' || this.pendingCaptureReset !== null) return
      if (event.data.byteLength !== CAPTURE_FRAME_BYTES || !this.socket ||
          this.socket.bufferedAmount + (this.options.v2 ? event.data.byteLength : 0) > SEND_BUFFER_BYTES) {
        // Truncating an arbitrary spoken command under pressure is unsafe.
        this.fail('Kết nối âm thanh bị chậm. Bạn có thể tiếp tục bằng tin nhắn.')
        return
      }
      try {
        if (this.socket.readyState === 1) this.socket.send(event.data)
      } catch { this.fail('Mất kết nối âm thanh. Bạn có thể tiếp tục bằng tin nhắn.') }
    }
  }

  private releaseMicrophone() {
    if (this.captureTimer !== undefined) {
      clearTimeout(this.captureTimer)
      this.timers.delete(this.captureTimer)
      this.captureTimer = undefined
    }
    const stream = this.stream, capture = this.capture
    this.capture = this.stream = undefined
    this.pendingCaptureReset = null
    stream?.getTracks().forEach(track => { track.onended = track.onmute = null; track.stop() })
    if (capture) {
      capture.onprocessorerror = capture.port.onmessageerror = capture.port.onmessage = null
      capture.port.close()
      capture.disconnect()
    }
    this.microphoneSource?.disconnect()
    this.filter?.disconnect()
    this.silent?.disconnect()
    this.microphoneSource = this.filter = this.silent = undefined
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
        else {
          this.stream = stream
          if (this.options.v2) {
            this.micStartedMonotonic = performance.now()
            this.update({ startedAt: Date.now() })
            // Loss during permission/setup is terminal too, before a ticket exists.
            for (const track of stream.getAudioTracks()) {
              track.onended = track.onmute = () => {
                if (this.stream === stream) this.fail(CAPTURE_LOST)
              }
            }
          }
        }
        return stream
      })
      await Promise.all([resumed, media])
      this.ensureOpen()
      const context = this.context
      if (!context.audioWorklet) throw new Error('unsupported_audio')
      await context.audioWorklet.addModule(workletUrl)
      this.ensureOpen()
      this.captureStream(this.stream!)
      this.ensureOpen()
      clearTimeout(mediaTimer)
      this.timers.delete(mediaTimer)
      this.update({ phase: 'connecting' })
      this.ticketRequested = true
      const ticket = await this.deps.ticket(this.conversationId, this.generation, this.controller.signal)
      if (this.closed) {
        void this.deps.revoke(this.conversationId, ticket.run_id).catch(() => {}).finally(this.saved)
        return
      }
      this.runId = ticket.run_id
      if (this.options.v2) {
        if (!Number.isFinite(ticket.max_seconds) || ticket.max_seconds <= 0) throw new Error('invalid_duration')
        this.callLimitMs = Math.min(MAX_CALL_MS, ticket.max_seconds * 1000)
        if (this.checkDeadline()) return
        this.later(() => this.checkDeadline(), Math.ceil(this.remainingCallTime()))
      }
      const url = new URL(`/api/mimi/conversations/${this.conversationId}/voice/${ticket.run_id}`, window.location.href)
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
      const socket = this.deps.socket(url.href)
      this.socket = socket
      socket.binaryType = 'arraybuffer'
      const connectionTimer = this.later(() => this.fail('Chưa kết nối được giọng nói. Bạn có thể thử lại hoặc nhắn Mimi.'), 15_000)
      socket.onopen = () => {
        if (this.closed) { socket.close(); return }
        if (this.checkDeadline()) { ticket.ticket = ''; return }
        try { socket.send(JSON.stringify({ type: 'ticket', ticket: ticket.ticket })) }
        catch { this.fail('Chưa kết nối được giọng nói. Bạn có thể tiếp tục bằng tin nhắn.') }
        finally { ticket.ticket = '' }
      }
      socket.onmessage = event => {
        if (this.closed) return
        if (event.data instanceof ArrayBuffer) {
          if (this.ending || this.state.phase === 'reconnecting' || this.checkDeadline()) return
          try { this.play(event.data) } catch { this.fail(PLAYBACK_FAILED) }
          return
        }
        try {
          if (typeof event.data !== 'string' || event.data.length > 32_768) throw new Error('invalid_frame')
          const message = JSON.parse(event.data)
          if (this.ending && message.type !== 'ended' && !(this.options.v2 && message.type === 'action_updated')) return
          if (!this.ending && message.type !== 'ended' && this.checkDeadline()) return
          if (message.type === 'ready') {
            if (this.ready || message.run_id !== this.runId) throw new Error('invalid_session')
            clearTimeout(connectionTimer)
            this.timers.delete(connectionTimer)
            this.ready = true
            this.update({ phase: 'listening', startedAt: this.state.startedAt ?? Date.now() })
            if (!this.options.v2) this.later(() => this.stop('Phiên giọng nói đã hết thời lượng. Bạn có thể bắt đầu phiên mới.'), ticket.max_seconds * 1000)
          } else if (message.type === 'interrupted') {
            this.clearPlayback()
            if (this.state.phase !== 'reconnecting') this.update({ phase: 'listening', caption: '', actionStatus: null })
          } else if (message.type === 'transcript' && ['user', 'assistant'].includes(message.role) && typeof message.text === 'string' && message.text.length <= 16_384) {
            if (this.state.phase === 'reconnecting') return
            const userSpoke = this.options.v2 && message.role === 'user' && !!message.text.trim()
            const nextTurn = userSpoke && !this.turnActive
            if (nextTurn) this.interruptedBeforeResume = false
            if (this.options.v2 && message.text.trim()) this.turnActive = true
            // Input fragments have no turn ID; never carry a write cue into user speech.
            this.update({ caption: message.text, captionRole: message.role,
              ...(userSpoke ? { actionStatus: null } : {}), ...(nextTurn ? { notice: null } : {}) })
          } else if (message.type === 'transcript_saved') {
            this.update({ caption: '' })
            this.saved()
          } else if (message.type === 'turn_complete') {
            // Audio may still be scheduled. Only source.onended means playback ended.
            this.turnActive = this.dropOutputUntilBoundary = false
            if (this.state.phase !== 'reconnecting' && !this.playing.size && !this.playbackBytes) this.update({ phase: 'listening' })
          } else if (this.options.v2 && this.ready && message.type === 'reconnecting') {
            this.pendingCaptureReset = null
            if (this.state.phase === 'reconnecting') return
            this.interruptedBeforeResume = this.turnActive || !!this.playing.size || !!this.playbackBytes
            this.clearPlayback()
            this.update({ phase: 'reconnecting', caption: '', actionStatus: null,
              notice: this.interruptedBeforeResume ? `Lượt vừa rồi có thể chưa hoàn tất. ${CHECK_SAVED_RESULT}` : CHECK_SAVED_RESULT })
          } else if (this.options.v2 && this.ready && message.type === 'resumed') {
            if (this.state.phase !== 'reconnecting') return
            if (!this.capture || performance.now() - this.lastCaptureAt >= CAPTURE_LOSS_MS) {
              this.fail(CAPTURE_LOST)
              return
            }
            this.turnActive = this.dropOutputUntilBoundary = false
            // MessagePort replies in order: frames queued before resume and
            // samples from before the worklet reset cannot become new input.
            const reset = this.pendingCaptureReset = ++this.captureResetSequence
            this.capture.port.postMessage({ captureReset: reset })
            this.later(() => { if (this.pendingCaptureReset === reset) this.fail(CAPTURE_LOST) }, CAPTURE_LOSS_MS)
            const resumeNotice = message.context_retained === false ? 'Đã nối lại. Một phần ngữ cảnh trước đó có thể thiếu.'
              : this.interruptedBeforeResume ? 'Đã nối lại. Lượt trước có thể chưa hoàn tất.' : 'Đã nối lại.'
            this.update({ phase: 'listening', actionStatus: null, notice: this.checkSavedNotice(resumeNotice) })
            this.saved(true)
          } else if (this.options.v2 && this.ready && message.type === 'action_updated' &&
            (message.status === 'preview' || message.status === 'applied' || message.status === 'undone')) {
            if (message.run_id !== undefined && message.run_id !== this.runId) throw new Error('invalid_session')
            if (!this.ending && this.state.phase !== 'reconnecting') this.update({ actionStatus: message.status })
            this.options.actionUpdated?.(message.status)
          } else if (message.type === 'ended') {
            const stopped = this.options.v2 ? this.state.notice : null
            this.finish(message.reason === 'voice_stopped' ? stopped
              : this.checkSavedNotice(this.disconnectNotice('Phiên giọng nói đã kết thúc. Bản chép lời có thể chưa đầy đủ; bạn vẫn có thể nhắn Mimi.')))
          } else if (message.type !== 'muted') {
            throw new Error('invalid_event')
          }
        } catch { this.fail('Kết nối giọng nói không hợp lệ. Bạn có thể tiếp tục bằng tin nhắn.') }
      }
      socket.onerror = () => this.fail(this.disconnectNotice('Mất kết nối giọng nói. Bản nháp được giữ; bạn có thể nhắn Mimi.'))
      socket.onclose = () => {
        if (!this.closed && !this.ending) this.fail(this.disconnectNotice('Phiên giọng nói bị ngắt. Bản chép lời có thể chưa đầy đủ; bạn có thể nhắn Mimi.'))
        else if (this.ending) this.finish(this.options.v2 ? this.state.notice : null)
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
    if (!context || !this.ready || !data.byteLength || data.byteLength % 2 || data.byteLength > MAX_AUDIO_FRAME_BYTES) throw new Error('invalid_pcm')
    if (this.options.v2) {
      if (this.dropOutputUntilBoundary) return
      this.turnActive = true
      const scheduledBytes = Math.max(0, this.nextPlayback - context.currentTime) * OUTPUT_BYTES_PER_SECOND
      if (this.playbackQueue.length >= V2_MAX_QUEUED_FRAMES ||
          this.playbackBytes + data.byteLength + scheduledBytes > V2_PLAYBACK_BUDGET) {
        // Abandon this response visibly, not isolated chunks within sentences.
        // Do not disconnect, replay the turn, or queue its tail behind newer audio.
        this.clearPlayback()
        this.dropOutputUntilBoundary = true
        this.update({ phase: 'listening', notice: this.checkSavedNotice('Âm thanh đến dồn dập nên không phát hết câu trả lời.') })
        return
      }
      this.playbackQueue.push({ data, offset: 0 })
      this.playbackBytes += data.byteLength
      this.pumpPlayback(context)
      return
    }
    const begin = Math.max(context.currentTime + 0.02, this.nextPlayback)
    const duration = data.byteLength / OUTPUT_BYTES_PER_SECOND
    if (begin + duration - context.currentTime > 15) throw new Error('playback_queue_limit')
    this.schedulePlayback(context, data, 0, data.byteLength, begin)
  }

  private pumpPlayback(context: AudioContext) {
    while (this.playbackQueue.length && this.playing.size < V2_MAX_PLAYING_NODES) {
      const frame = this.playbackQueue[0]
      const length = Math.min(V2_PLAYBACK_CHUNK, frame.data.byteLength - frame.offset)
      const begin = Math.max(this.playing.size ? context.currentTime : context.currentTime + 0.02, this.nextPlayback)
      if (begin + length / OUTPUT_BYTES_PER_SECOND - context.currentTime > V2_PLAYBACK_LEAD) return
      this.schedulePlayback(context, frame.data, frame.offset, length, begin)
      frame.offset += length
      this.playbackBytes -= length
      if (frame.offset === frame.data.byteLength) this.playbackQueue.shift()
    }
  }

  private schedulePlayback(context: AudioContext, data: ArrayBuffer, offset: number, length: number, begin: number) {
    const buffer = context.createBuffer(1, length / 2, 24_000)
    const samples = buffer.getChannelData(0)
    const view = new DataView(data, offset, length)
    for (let i = 0; i < samples.length; i++) samples[i] = view.getInt16(i * 2, true) / 32768
    const source = context.createBufferSource()
    source.buffer = buffer
    source.connect(context.destination)
    this.playing.add(source)
    source.onended = () => {
      if (!this.playing.delete(source)) return
      source.disconnect()
      if (this.closed || this.ending || this.state.phase === 'reconnecting') return
      if (this.checkDeadline()) return
      if (this.options.v2) {
        try { this.pumpPlayback(context) } catch { this.fail(PLAYBACK_FAILED); return }
      }
      if (!this.playing.size && !this.playbackBytes) this.update({ phase: 'listening' })
    }
    source.start(begin)
    this.nextPlayback = begin + length / OUTPUT_BYTES_PER_SECOND
    if (this.state.phase !== 'speaking') this.update({ phase: 'speaking' })
  }
  private clearPlayback() {
    for (const source of this.playing) {
      source.onended = null
      try { source.stop(); source.disconnect() } catch { /* Already ended. */ }
    }
    this.playing.clear()
    this.playbackQueue = []
    this.playbackBytes = 0
    this.nextPlayback = 0
  }
  mute() {
    if (this.options.v2) {
      this.stop()
      return
    }
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
    const recoveryNotice = this.checkSavedNotice(notice)
    this.dispose(true)
    this.update({ phase: 'error', notice: recoveryNotice, caption: '', actionStatus: null })
  }
  stop(notice: string | null = null) {
    if (this.closed || this.ending) return
    if (notice) notice = this.checkSavedNotice(notice)
    if (this.ready && this.socket?.readyState === 1) {
      this.ending = true
      this.releaseAudio()
      this.update({ phase: 'ending', notice, caption: '', actionStatus: null })
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
    this.update({ phase: 'ended', notice, caption: '', actionStatus: null })
  }
  private releaseAudio() {
    this.clearPlayback()
    this.releaseMicrophone()
    if (this.context && this.context.state !== 'closed') void this.context.close().catch(() => {})
    this.context = undefined
  }
  private dispose(revoke: boolean) {
    if (this.closed) return
    const reconcileUnknown = this.options.v2 && this.ready
    const refresh = () => { if (reconcileUnknown) this.saved(true); else this.saved() }
    this.closed = true
    this.controller.abort()
    for (const timer of this.timers) clearTimeout(timer)
    this.timers.clear()
    this.releaseAudio()
    if (this.socket) {
      this.socket.onmessage = this.socket.onerror = this.socket.onclose = null
      try { this.socket.close(1000) } catch { /* CONNECTING will close in onopen. */ }
    }
    // A write may have committed even when its action_updated control never arrived.
    if (revoke && this.runId) void this.deps.revoke(this.conversationId, this.runId).catch(() => {}).finally(refresh)
    else if (this.ticketRequested) refresh()
    this.ready = false
  }
}
