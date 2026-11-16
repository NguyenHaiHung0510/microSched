import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { expect, test, vi } from 'vitest'

test('capture reset acknowledges in order and does not mix pre-resume samples into new PCM', () => {
  const port = { onmessage: vi.fn<(event: { data: unknown }) => void>(), postMessage: vi.fn() }
  let Capture!: new () => { process: (inputs: Float32Array[][]) => boolean }
  runInNewContext(readFileSync(new URL('../src/mimi-pcm-worklet.js', import.meta.url), 'utf8'), {
    AudioWorkletProcessor: class { port = port },
    sampleRate: 16_000,
    registerProcessor: (_name: string, Processor: typeof Capture) => { Capture = Processor },
  })
  const capture = new Capture()
  capture.process([[new Float32Array(640).fill(0.75)]])
  capture.process([[new Float32Array(320).fill(0.75)]])
  port.onmessage({ data: { captureReset: 1 } })
  capture.process([[new Float32Array(320).fill(-0.5)]])
  expect(port.postMessage.mock.calls).toHaveLength(2)
  expect(port.postMessage.mock.calls[1][0]).toEqual({ captureReset: 1 })
  capture.process([[new Float32Array(320).fill(-0.5)]])
  const fresh = new DataView(port.postMessage.mock.calls[2][0])
  expect(fresh.byteLength).toBe(1280)
  expect(Array.from({ length: 640 }, (_, i) => fresh.getInt16(i * 2, true)).every(sample => sample === -16384)).toBe(true)
})
