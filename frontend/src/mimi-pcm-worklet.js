/* Runs only inside AudioWorkletGlobalScope. Hardware-rate mono -> 16 kHz PCM. */
class MimiPcmCapture extends AudioWorkletProcessor {
  constructor() {
    super()
    this.position = 0
    this.sum = 0
    this.weight = 0
    this.frame = new Int16Array(640) // 40 ms at the wire rate.
    this.index = 0
    this.port.onmessage = ({ data }) => {
      if (!Number.isSafeInteger(data?.captureReset)) return
      this.position = this.sum = this.weight = this.index = 0
      this.port.postMessage({ captureReset: data.captureReset })
    }
  }
  process(inputs) {
    const channel = inputs[0]?.[0]
    if (!channel) return true
    const ratio = sampleRate / 16000
    for (const sample of channel) {
      let available = 1
      while (available > 0) {
        const take = Math.min(available, ratio - this.position)
        this.sum += sample * take
        this.weight += take
        this.position += take
        available -= take
        if (this.position >= ratio - 1e-9) {
          const value = Math.max(-1, Math.min(1, this.sum / this.weight))
          this.frame[this.index++] = Math.round(value * (value < 0 ? 32768 : 32767))
          this.position = this.sum = this.weight = 0
          if (this.index === this.frame.length) {
            // DataView defines little endian even on a non-little-endian host.
            const bytes = new ArrayBuffer(this.frame.length * 2)
            const view = new DataView(bytes)
            for (let i = 0; i < this.frame.length; i++) view.setInt16(i * 2, this.frame[i], true)
            this.port.postMessage(bytes, [bytes])
            this.index = 0
          }
        }
      }
    }
    return true
  }
}
registerProcessor('mimi-pcm-capture', MimiPcmCapture)
