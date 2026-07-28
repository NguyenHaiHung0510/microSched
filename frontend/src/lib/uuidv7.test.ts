import { describe, expect, it } from 'vitest'

import { uuidv7 } from './uuidv7'

describe('uuidv7', () => {
  it('generates 10,000 unique, strictly increasing UUIDv7 values', () => {
    const ids = Array.from({ length: 10_000 }, uuidv7)

    expect(new Set(ids).size).toBe(ids.length)
    for (let index = 1; index < ids.length; index += 1) {
      expect(ids[index] > ids[index - 1]).toBe(true)
    }
    for (const id of ids) {
      expect(id[14]).toBe('7')
      expect(Number.parseInt(id[19], 16) & 0b1100).toBe(0b1000)
    }
  })
})
