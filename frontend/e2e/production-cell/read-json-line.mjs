import { createInterface } from 'node:readline'

/** The caller sends one canonical JSON line; Docker may keep stdin open. */
export async function readJsonLine(input = process.stdin) {
  const lines = createInterface({ input, crlfDelay: Infinity })
  try {
    for await (const line of lines) {
      if (Buffer.byteLength(line, 'utf8') > 65536) throw new Error('stdin payload exceeds64KiB')
      return JSON.parse(line)
    }
    throw new Error('stdin payload missing')
  } finally {
    lines.close()
    input.pause()
  }
}
