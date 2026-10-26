import { describe, expect, it } from 'vitest'
import { singleLineTitle } from '../src/task-title'

describe('title soft wrapping preserves text-input semantics', () => {
  it('removes only CR/LF and preserves spaces, Vietnamese and emoji', () => {
    expect(singleLineTitle('  ĐỀ\r\nCƯƠNG\n📚  ')).toBe('  ĐỀCƯƠNG📚  ')
    expect(singleLineTitle('  ế ữ ộ ằ 📚  ')).toBe('  ế ữ ộ ằ 📚  ')
  })
})
