import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { onMimiSessionPurge, purgeMimiSession } from './mimi-session-boundary'
import { MimiVoiceSession, type VoiceDependencies, type VoiceState } from './mimi-voice'

beforeEach(() => vi.stubGlobal('window', { location: { href: 'https://mimi.example.test/' } }))
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

function fixture() {
  const playback: Array<ReturnType<typeof source>> = []
  function source() { return { connect: vi.fn(), start: vi.fn(), stop: vi.fn(), disconnect: vi.fn(), onended: null } }
  const node = () => ({ connect: vi.fn(child => child), disconnect: vi.fn() })
  const track = () => ({ enabled: true, stop: vi.fn(), onended: null })
  const first = track(), second = track()
  const stream = (item: ReturnType<typeof track>) => ({ getTracks: () => [item], getAudioTracks: () => [item] })
  const captures: Array<{ port: { onmessage: ((e: { data: unknown }) => void) | null; close: () => void } }> = []
  const context = {
    resume: vi.fn(async () => {}), close: vi.fn(async () => {}), state: 'running', currentTime: 1,
    destination: {}, audioWorklet: { addModule: vi.fn(async () => {}) },
    createBuffer: vi.fn((_channels, frames) => ({ getChannelData: () => new Float32Array(frames) })),
    createBufferSource: () => { const item = source(); playback.push(item); return item },
    createMediaStreamSource: node, createGain: () => ({ ...node(), gain: { value: 1 } }),
    createBiquadFilter: () => ({ ...node(), frequency: { value: 0 }, Q: { value: 0 } }),
  }
  const socket = {
    readyState: 1, bufferedAmount: 0, send: vi.fn(), close: vi.fn(),
    onopen: null as (() => void) | null, onmessage: null as ((event: { data: unknown }) => void) | null,
    onerror: null as (() => void) | null,
  }
  const deps = {
    audioContext: () => context as unknown as AudioContext,
    microphone: vi.fn().mockResolvedValueOnce(stream(first)).mockResolvedValueOnce(stream(second)),
    worklet: () => {
      const item = { ...node(), port: { onmessage: null, close: vi.fn() } }
      captures.push(item)
      return item as unknown as AudioWorkletNode
    },
    ticket: vi.fn(async () => ({ ticket: 'fixture-token', run_id: 'test-run', expires_in: 30, max_seconds: 90 })),
    revoke: vi.fn(async () => {}), socket: vi.fn(() => socket as unknown as WebSocket),
  } satisfies VoiceDependencies
  const updates: VoiceState[] = []
  const saved = vi.fn()
  const voice = new MimiVoiceSession('test-chat', 1, state => updates.push(state), saved, deps)
  const message = (data: unknown) => socket.onmessage?.({ data: data instanceof ArrayBuffer ? data : JSON.stringify(data) })
  return { voice, message, socket, deps, saved, updates, playback, first, second, stream, context, captures }
}

test('full duplex preserves unrelated playback while muted; interrupted clears every queued source', async () => {
  const f = fixture()
  await f.voice.start()
  f.socket.onopen?.()
  expect(f.deps.socket.mock.calls).toEqual([['wss://mimi.example.test/api/mimi/conversations/test-chat/voice/test-run']])
  expect(f.socket.send).toHaveBeenCalledWith('{"type":"ticket","ticket":"fixture-token"}')
  f.message({ type: 'ready', run_id: 'test-run' })
  const frame = new ArrayBuffer(1280)
  f.message(new ArrayBuffer(1920))
  f.message(new ArrayBuffer(1920))
  f.captures[0].port.onmessage?.({ data: frame })
  expect(f.socket.send).toHaveBeenCalledWith(frame)
  expect(f.context.createBuffer).toHaveBeenCalledWith(1, 960, 24_000)
  f.voice.mute()
  expect(f.first.stop).toHaveBeenCalledOnce()
  expect(f.socket.send).toHaveBeenLastCalledWith('{"type":"mute","muted":true}')
  expect(f.captures[0].port.onmessage).toBeNull()
  expect(f.playback[0].stop).not.toHaveBeenCalled()
  f.message({ type: 'interrupted' })
  expect(f.playback.every(source => source.stop.mock.calls.length === 1)).toBe(true)
  f.voice.mute()
  await Promise.resolve()
  expect(f.socket.send).toHaveBeenLastCalledWith('{"type":"mute","muted":false}')
  f.voice.stop()
  expect(f.second.stop).toHaveBeenCalledOnce()
  expect(f.context.close).toHaveBeenCalledOnce()
  expect(f.socket.send).toHaveBeenLastCalledWith('{"type":"stop"}')
  f.message({ type: 'ended', reason: 'voice_stopped' })
  expect(f.socket.close).toHaveBeenCalledOnce()
  expect(f.saved).toHaveBeenCalledOnce()
  expect(f.updates.at(-1)?.phase).toBe('ended')
})

test('permission denial does not mint a ticket and returns the fallback message', async () => {
  const f = fixture()
  f.deps.microphone.mockReset().mockRejectedValueOnce(new DOMException('fixture', 'NotAllowedError'))
  await f.voice.start()
  expect(f.updates.at(-1)).toMatchObject({ phase: 'error', notice: expect.stringContaining('Chưa được phép dùng micro') })
  expect(f.deps.ticket).not.toHaveBeenCalled()
  expect(f.context.close).toHaveBeenCalledOnce()
})

test('session purge stops a late microphone grant and never sends it', async () => {
  const f = fixture()
  let resolveMedia: ((value: unknown) => void) | undefined
  f.deps.microphone.mockReset().mockImplementationOnce(() => new Promise(resolve => { resolveMedia = resolve }))
  const client = new QueryClient()
  const unsubscribe = onMimiSessionPurge(client, () => f.voice.cancel())
  // The test has no DOM/Web Storage. The actual browser also clears selected chat.
  vi.stubGlobal('window', undefined)
  const start = f.voice.start()
  purgeMimiSession(client)
  resolveMedia?.(f.stream(f.first))
  await start
  expect(f.first.stop).toHaveBeenCalledOnce()
  expect(f.deps.ticket).not.toHaveBeenCalled()
  expect(f.context.close).toHaveBeenCalledOnce()
  unsubscribe()
})

test('route change during ticket acquisition revokes late capability without opening a socket', async () => {
  const f = fixture()
  let completeTicket: ((ticket: Awaited<ReturnType<VoiceDependencies['ticket']>>) => void) | undefined
  f.deps.ticket.mockImplementationOnce(() => new Promise(resolve => { completeTicket = resolve }))
  const start = f.voice.start()
  await vi.waitFor(() => expect(f.deps.ticket).toHaveBeenCalledOnce())
  f.voice.cancel()
  completeTicket?.({ ticket: 'known-fixture', run_id: 'late-run', expires_in: 30, max_seconds: 90 })
  await start
  expect(f.deps.revoke).toHaveBeenCalledWith('test-chat', 'late-run')
  expect(f.deps.socket).not.toHaveBeenCalled()
  expect(f.first.stop).toHaveBeenCalledOnce()
})

test('socket error closes all resources without reconnect', async () => {
  const f = fixture()
  await f.voice.start()
  f.socket.onopen?.()
  f.message({ type: 'ready', run_id: 'test-run' })
  f.socket.onerror?.()
  expect(f.updates.at(-1)).toMatchObject({ phase: 'error', notice: expect.stringContaining('Bản nháp') })
  expect(f.first.stop).toHaveBeenCalledOnce()
  expect(f.socket.close).toHaveBeenCalledOnce()
  expect(f.deps.socket).toHaveBeenCalledOnce()
  expect(f.deps.revoke).toHaveBeenCalledWith('test-chat', 'test-run')
})
