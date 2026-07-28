let lastTimestamp = -1
let sequence = 0n

const RANDOM_MASK = (1n << 74n) - 1n

function random74Bits(): bigint {
  const bytes = new Uint8Array(10)
  crypto.getRandomValues(bytes)
  let value = 0n
  for (const byte of bytes) value = (value << 8n) | BigInt(byte)
  return value & RANDOM_MASK
}

export function uuidv7(): string {
  const now = Date.now()
  const timestamp = Math.max(now, lastTimestamp)

  if (timestamp === lastTimestamp) {
    sequence = (sequence + 1n) & RANDOM_MASK
  } else {
    lastTimestamp = timestamp
    sequence = random74Bits()
  }

  const randomA = Number((sequence >> 62n) & 0xfffn)
  const randomB = sequence & ((1n << 62n) - 1n)
  const high = (BigInt(timestamp) << 16n) | 0x7000n | BigInt(randomA)
  const low = 0x8000000000000000n | randomB
  const hex = high.toString(16).padStart(16, '0') + low.toString(16).padStart(16, '0')

  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
