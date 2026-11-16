import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { onMimiSessionPurge, purgeMimiSession } from './mimi-session-boundary'
import { MimiVoiceSession, type VoiceDependencies, type VoiceState } from './mimi-voice'
import { refreshMimiVoiceAction } from './useMimiVoice'

beforeEach(() => vi.stubGlobal('window', { location: { href: 'https://mimi.example.test/' } }))
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

function fixture(v2 = false) {
  const playback: Array<ReturnType<typeof source>> = []
  function source() { return { connect: vi.fn(), start: vi.fn(), stop: vi.fn(), disconnect: vi.fn(), onended: null as (() => void) | null } }
  const node = () => ({ connect: vi.fn(child => child), disconnect: vi.fn() })
  const track = () => ({ enabled: true, readyState: 'live', muted: false, stop: vi.fn(), onended: null as (() => void) | null })
  const first = track(), second = track()
  const stream = (item: ReturnType<typeof track>) => ({ getTracks: () => [item], getAudioTracks: () => [item] })
  const captures: Array<{
    port: { onmessage: ((e: { data: unknown }) => void) | null; close: () => void; postMessage: ReturnType<typeof vi.fn> }
  }> = []
  const samples: Float32Array[] = []
  const context = {
    resume: vi.fn(async () => {}), close: vi.fn(async () => {}), state: 'running', currentTime: 1,
    destination: {}, audioWorklet: { addModule: vi.fn(async () => {}) },
    createBuffer: vi.fn((_channels, frames) => {
      const data = new Float32Array(frames)
      samples.push(data)
      return { getChannelData: () => data }
    }),
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
      const item = { ...node(), port: { onmessage: null, close: vi.fn(), postMessage: vi.fn() } }
      captures.push(item)
      return item as unknown as AudioWorkletNode
    },
    ticket: vi.fn(async () => ({ ticket: 'fixture-token', run_id: 'test-run', expires_in: 30, max_seconds: 90 })),
    revoke: vi.fn(async () => {}), socket: vi.fn(() => socket as unknown as WebSocket),
  } satisfies VoiceDependencies
  const updates: VoiceState[] = []
  const saved = vi.fn()
  const actionUpdated = vi.fn()
  const voice = new MimiVoiceSession('test-chat', 1, state => updates.push(state), saved, deps, { v2, actionUpdated })
  const message = (data: unknown) => socket.onmessage?.({ data: data instanceof ArrayBuffer ? data : JSON.stringify(data) })
  return { voice, message, socket, deps, saved, updates, playback, first, second, stream, context, captures, samples, actionUpdated }
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

async function connectV2() {
  const f = fixture(true)
  f.deps.ticket.mockResolvedValueOnce({ ticket: 'v2', run_id: 'test-run', expires_in: 30, max_seconds: 5400 })
  await f.voice.start()
  f.socket.onopen?.()
  f.message({ type: 'ready', run_id: 'test-run' })
  return f
}

test('V2 plays a 16-second output burst in order without closing the healthy call', async () => {
  const f = await connectV2()
  for (let n = 1; n <= 8; n++) {
    const pcm = new ArrayBuffer(96_000)
    const frame = new DataView(pcm)
    for (let i = 0; i < frame.byteLength; i += 2) frame.setInt16(i, n, true)
    f.message(pcm)
  }
  f.message({ type: 'turn_complete' })
  expect(f.socket.close).not.toHaveBeenCalled()
  expect(f.playback.length).toBeLessThan(8) // Only schedule a short window, not the whole burst.
  for (let i = 0; i < f.playback.length; i++) {
    f.context.currentTime = f.playback[i].start.mock.calls[0][0] + f.samples[i].length / 24_000
    f.playback[i].onended?.()
  }
  expect(f.samples.reduce((total, samples) => total + samples.length, 0)).toBe(16 * 24_000)
  const frameOrder = f.samples.map(samples => samples[0] * 32768).filter((tag, index, tags) => !index || tag !== tags[index - 1])
  expect(frameOrder).toEqual([1, 2, 3, 4, 5, 6, 7, 8])
  expect(f.updates.at(-1)?.phase).toBe('listening')
  f.voice.cancel()
})

test('V2 mic-off releases capture and playback, and late provider controls cannot reactivate it', async () => {
  const f = await connectV2()
  f.message(new ArrayBuffer(1920))
  f.voice.mute()
  expect(f.first.stop).toHaveBeenCalledOnce()
  expect(f.playback[0].stop).toHaveBeenCalledOnce()
  expect(f.socket.send).toHaveBeenLastCalledWith('{"type":"stop"}')
  f.message({ type: 'reconnecting' })
  f.message({ type: 'resumed' })
  f.message(new ArrayBuffer(1920))
  expect(f.playback).toHaveLength(1)
  expect(f.deps.microphone).toHaveBeenCalledTimes(1)
  expect(f.deps.socket).toHaveBeenCalledTimes(1)
  f.message({ type: 'ended', reason: 'voice_stopped' })
  expect(f.updates.at(-1)?.phase).toBe('ended')
})

test('V2 provider resumption keeps the original live mic and clock without replay and asks to check the saved result', async () => {
  vi.useFakeTimers()
  const f = await connectV2()
  const startedAt = f.updates.at(-1)?.startedAt
  const pcm = new ArrayBuffer(1280)
  f.captures[0].port.onmessage?.({ data: pcm })
  f.message({ type: 'transcript', role: 'user', text: 'Synthetic input' })
  f.message({ type: 'reconnecting' })
  expect(f.updates.at(-1)?.phase).toBe('reconnecting')
  f.captures[0].port.onmessage?.({ data: pcm })
  expect(f.socket.send.mock.calls.filter(([data]) => data === pcm)).toHaveLength(1)
  f.message({ type: 'resumed', context_retained: true })
  expect(f.updates.at(-1)).toMatchObject({ phase: 'listening', startedAt, notice: expect.stringContaining('kiểm tra') })
  expect(f.updates.at(-1)?.notice).not.toContain('nhắc lại')
  expect(f.saved).toHaveBeenCalledWith(true)
  f.captures[0].port.onmessage?.({ data: pcm }) // Old MessagePort task delivered after WS resumed.
  expect(f.socket.send.mock.calls.filter(([data]) => data === pcm)).toHaveLength(1)
  f.captures[0].port.onmessage?.({ data: f.captures[0].port.postMessage.mock.lastCall?.[0] })
  f.captures[0].port.onmessage?.({ data: pcm })
  expect(f.socket.send.mock.calls.filter(([data]) => data === pcm)).toHaveLength(2)
  expect(f.deps.microphone).toHaveBeenCalledTimes(1)
  expect(f.deps.ticket).toHaveBeenCalledTimes(1)
  expect(f.deps.socket).toHaveBeenCalledTimes(1)
  f.voice.cancel()
})

test('V2 overload aborts the affected response visibly and admits audio only after its boundary', async () => {
  const f = await connectV2()
  for (let i = 0; i < 8; i++) f.message(new ArrayBuffer(240_000))
  expect(f.playback.every(source => source.stop.mock.calls.length === 1)).toBe(true)
  expect(f.updates.at(-1)?.notice).toContain('kết quả đã lưu')
  expect(f.socket.close).not.toHaveBeenCalled()
  const before = f.playback.length
  f.message(new ArrayBuffer(1920))
  expect(f.playback).toHaveLength(before)
  f.message({ type: 'turn_complete' })
  f.message(new ArrayBuffer(1920))
  expect(f.playback).toHaveLength(before + 1)
  f.voice.cancel()
})

test('V2 interruption clears scheduled and waiting audio, with no restart from an old callback', async () => {
  const f = await connectV2()
  f.message(new ArrayBuffer(240_000))
  const stalePlayback = f.playback[0].onended
  const before = f.playback.length
  f.message({ type: 'interrupted' })
  stalePlayback?.()
  expect(f.playback).toHaveLength(before)
  expect(f.playback.every(source => source.stop.mock.calls.length === 1)).toBe(true)
  expect(f.updates.at(-1)?.phase).toBe('listening')
  expect(f.socket.close).not.toHaveBeenCalled()
  f.voice.cancel()
})

test('V2 accepts silent background PCM but stops after loss of capture even with a live socket', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('document', { hidden: true, visibilityState: 'hidden' })
  const f = await connectV2()
  const frame = new ArrayBuffer(1280)
  for (let i = 0; i < 4; i++) {
    await vi.advanceTimersByTimeAsync(1500)
    f.captures[0].port.onmessage?.({ data: frame })
  }
  expect(f.socket.send.mock.calls.filter(([data]) => data === frame)).toHaveLength(4)
  expect(f.socket.close).not.toHaveBeenCalled()
  f.message(new ArrayBuffer(1920))
  await vi.advanceTimersByTimeAsync(5000)
  expect(f.updates.at(-1)).toMatchObject({ phase: 'error', notice: expect.stringContaining('Micro đã ngắt') })
  expect(f.first.stop).toHaveBeenCalledOnce()
  expect(f.playback[0].stop).toHaveBeenCalledOnce()
  expect(f.deps.revoke).toHaveBeenCalledWith('test-chat', 'test-run')
  expect(f.socket.close).toHaveBeenCalledOnce()
})

test('V2 track loss stops immediately, including during a provider reconnect', async () => {
  const f = await connectV2()
  f.message({ type: 'reconnecting' })
  f.first.onended?.()
  f.message({ type: 'resumed' })
  expect(f.updates.at(-1)?.phase).toBe('error')
  expect(f.first.stop).toHaveBeenCalledOnce()
  expect(f.captures[0].port.onmessage).toBeNull()
  expect(f.deps.socket).toHaveBeenCalledTimes(1)
})

test.each([90, 5400])('V2 honors the original absolute cap (%s seconds) after resume', async maxSeconds => {
  vi.useFakeTimers()
  vi.setSystemTime(1_000_000)
  const f = fixture(true)
  f.deps.ticket.mockResolvedValueOnce({ ticket: 'limited', run_id: 'test-run', expires_in: 30, max_seconds: maxSeconds })
  await f.voice.start()
  f.socket.onopen?.()
  f.message({ type: 'ready', run_id: 'test-run' })
  const startedAt = f.updates.at(-1)?.startedAt
  const frame = new ArrayBuffer(1280)
  vi.setSystemTime(1_000_000 + maxSeconds * 1000 - 1)
  f.captures[0].port.onmessage?.({ data: frame })
  f.message({ type: 'reconnecting' })
  f.message({ type: 'resumed' })
  expect(f.updates.at(-1)).toMatchObject({ phase: 'listening', startedAt })
  vi.setSystemTime(1_000_000 + maxSeconds * 1000)
  f.captures[0].port.onmessage?.({ data: frame })
  expect(f.socket.send).toHaveBeenLastCalledWith('{"type":"stop"}')
  expect(f.first.stop).toHaveBeenCalledOnce()
  expect(f.updates.at(-1)).toMatchObject({ phase: 'ending', notice: expect.stringContaining('hết thời lượng') })
  f.voice.cancel()
})

test('V2 accepts server action statuses only and teardown cannot publish a late event', async () => {
  const f = await connectV2()
  for (const status of ['preview', 'applied', 'undone']) {
    f.message({ type: 'action_updated', status })
    expect(f.updates.at(-1)?.actionStatus).toBe(status)
    expect(f.actionUpdated).toHaveBeenLastCalledWith(status)
  }
  const staleSocketCallback = f.socket.onmessage
  f.voice.cancel()
  staleSocketCallback?.({ data: JSON.stringify({ type: 'action_updated', status: 'applied' }) })
  expect(f.actionUpdated).toHaveBeenCalledTimes(3)
  expect(f.deps.socket).toHaveBeenCalledTimes(1)
})

test('V2 no-write control statuses keep the call open without claiming or invalidating a saved mutation', async () => {
  const f = await connectV2()
  const client = new QueryClient()
  const tasks = ['tasks', 'list'], calendar = ['calendar', 'tasks', 'range']
  const conversation = ['mimi', 'conversation', 'test-chat']
  for (const status of ['rejected', 'needs_clarification'] as const) {
    for (const key of [tasks, calendar, conversation]) client.setQueryData(key, { fixture: 'server state' })
    f.message({ type: 'action_updated', status, run_id: 'test-run' })
    expect(f.updates.at(-1)).toMatchObject({ phase: 'listening', actionStatus: status })
    expect(f.actionUpdated).toHaveBeenLastCalledWith(status)
    expect(f.socket.close).not.toHaveBeenCalled()
    expect(f.socket.send.mock.calls).toEqual([['{"type":"ticket","ticket":"v2"}']])
    await refreshMimiVoiceAction(client, 0, 'test-chat', status)
    expect(client.getQueryState(conversation)?.isInvalidated).toBe(true)
    for (const key of [tasks, calendar]) {
      expect(client.getQueryState(key)?.isInvalidated).toBe(false)
      expect(client.getQueryData(key)).toEqual({ fixture: 'server state' })
    }
  }
  f.voice.cancel()
  client.clear()
})

test('applied, undone and unknown outcomes refresh Tasks and Calendar; preview only refreshes conversation', async () => {
  const client = new QueryClient()
  const conversation = ['mimi', 'conversation', 'test-chat']
  const tasks = ['tasks', 'list']
  const calendar = ['calendar', 'tasks', 'range']
  const unrelated = [['mimi', 'conversation', 'other'], ['mimi', 'configuration'], ['calendar', 'events']]
  for (const key of [conversation, tasks, calendar, ...unrelated]) client.setQueryData(key, { fixture: 'server state' })
  await refreshMimiVoiceAction(client, 0, 'test-chat', 'preview')
  expect(client.getQueryState(conversation)?.isInvalidated).toBe(true)
  expect(client.getQueryState(tasks)?.isInvalidated).toBe(false)
  expect(client.getQueryState(calendar)?.isInvalidated).toBe(false)
  for (const status of ['applied', 'undone', 'unknown'] as const) {
    for (const key of [tasks, calendar]) client.setQueryData(key, { fixture: 'server state' })
    await refreshMimiVoiceAction(client, 0, 'test-chat', status)
    for (const key of [tasks, calendar]) {
      expect(client.getQueryState(key)?.isInvalidated).toBe(true)
      expect(client.getQueryData(key)).toEqual({ fixture: 'server state' })
    }
  }
  for (const key of unrelated) expect(client.getQueryState(key)?.isInvalidated).toBe(false)
  client.clear()
})

test('V2 socket failure after the turn boundary warns to check for a saved change', async () => {
  const f = await connectV2()
  f.message({ type: 'turn_complete' })
  f.socket.onerror?.()
  expect(f.updates.at(-1)).toMatchObject({ phase: 'error', notice: expect.stringContaining('kết quả đã lưu') })
  expect(f.updates.at(-1)?.notice).not.toContain('nhắc lại')
  expect(f.deps.socket).toHaveBeenCalledTimes(1)
})

test('V2 clears an action cue on new speech, reconnection and End without suppressing committed events', async () => {
  const f = await connectV2()
  f.message({ type: 'action_updated', status: 'applied' })
  f.message({ type: 'transcript', role: 'user', text: 'Synthetic next utterance' })
  expect(f.updates.at(-1)?.actionStatus).toBeNull()
  f.message({ type: 'action_updated', status: 'undone' })
  f.message({ type: 'reconnecting' })
  f.message({ type: 'action_updated', status: 'applied' })
  expect(f.updates.at(-1)?.actionStatus).toBeNull()
  f.message({ type: 'resumed', context_retained: false })
  expect(f.updates.at(-1)).toMatchObject({ actionStatus: null, notice: expect.stringContaining('ngữ cảnh') })
  f.message({ type: 'action_updated', status: 'preview' })
  f.voice.stop()
  f.message({ type: 'action_updated', status: 'applied' })
  expect(f.updates.at(-1)).toMatchObject({ phase: 'ending', actionStatus: null })
  expect(f.actionUpdated).toHaveBeenCalledTimes(5)
  f.message({ type: 'ended', reason: 'voice_stopped' })
  expect(f.updates.at(-1)).toMatchObject({ phase: 'ended', actionStatus: null })
})

test.each(['collapse', 'stop', 'error'])('V2 %s invalidates read caches even if the committed action event was lost', async exit => {
  const f = await connectV2()
  if (exit === 'collapse') f.voice.cancel()
  if (exit === 'stop') {
    f.voice.stop()
    f.message({ type: 'ended', reason: 'voice_stopped' })
  }
  if (exit === 'error') f.socket.onerror?.()
  await vi.waitFor(() => expect(f.saved.mock.calls).toEqual([[true]]))
  expect(f.actionUpdated).not.toHaveBeenCalled()
  expect(f.deps.socket).toHaveBeenCalledTimes(1)
  f.voice.cancel()
  expect(f.saved).toHaveBeenCalledOnce()
})
