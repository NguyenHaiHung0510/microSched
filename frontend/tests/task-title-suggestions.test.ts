import { describe, expect, it } from 'vitest'
import { rankTitleSuggestions, titleCandidates } from '../src/task-title-suggestions'
import { sanitizeSnapshot } from '../src/outbox/public-cache'
import type { PersistedClient } from '@tanstack/query-persist-client-core'

const history = [
  { title: '[TRAINING] upper body', count: 3 },
  { title: '[TRAINING] lower body', count: 8 },
  { title: '[TRAINING] soul', count: 25 },
  { title: 'Đọc sách', count: 1 },
  { title: 'Đọc sách buổi tối', count: 90 },
  { title: 'Sách đọc thêm', count: 100 },
  { title: 'Đọc sánh', count: 200 },
]
const candidates = titleCandidates(history)
const rank = (value: string) => rankTitleSuggestions(value, candidates)

describe('title matching without writes or a model', () => {
  it('offers a derived bare group for a typo, then progressively completes the title', () => {
    expect(rank('trainjing')[0]).toMatchObject({ title: '[TRAINING]', kind: 'group', tier: 3 })
    expect(rank('[TRAINING] upp').map(row => row.title)).toEqual(['[TRAINING] upper body'])
    expect(rank('body upper training')[0].title).toBe('[TRAINING] upper body')
  })

  it('keeps exact > prefix > reordered tokens > typo regardless of frequency', () => {
    expect(rank('doc sach').map(row => row.title)).toEqual([
      'Đọc sách', 'Đọc sách buổi tối', 'Sách đọc thêm', 'Đọc sánh',
    ])
    expect(rank('DOC SÁCH')[0].tier).toBe(0)
    expect(rank('training')[0].title).toBe('[TRAINING]')
    expect(rank('training')[1].title).toBe('[TRAINING] soul')
  })

  it.each(['', ' ', 'a', '[', 'zx', 'zzzzzz', 'training qz', 'upper upper', 'a'.repeat(161)])(
    'keeps weak/unrelated input free-form: %s', value => expect(rank(value)).toEqual([]),
  )

  it('recognizes transposition and accent variants without duplicating normalized candidates', () => {
    expect(rank('trianing')[0].title).toBe('[TRAINING]')
    const variants = titleCandidates([{ title: 'ĐỌC SÁCH', count: 1 }, { title: 'đọc sách', count: 2 }])
    expect(rankTitleSuggestions('doc sach', variants)).toHaveLength(1)
    expect(rankTitleSuggestions('doc sach', variants)[0].count).toBe(3)
  })

  it('uses only supplied titles and excludes ciphertext, whitespace and invalid counts', () => {
    expect(titleCandidates([
      { title: 'enc:v1:never-decrypt', count: 1 }, { title: ' ', count: 1 },
      { title: 'Bad count', count: 0 }, { title: 'Bad count', count: 513 },
    ])).toEqual([])
    expect(rank('<script>')).toEqual([])
    expect(rankTitleSuggestions('🚲', titleCandidates([{ title: '🚲', count: 1 }]))).toEqual([])
  })

  it('never persists the source in the existing IndexedDB public query cache', () => {
    const snapshot = { timestamp: Date.now(), buster: '', clientState: {
      mutations: [], queries: [{ queryKey: ['tasks', 'title-suggestions', 'synthetic-session'],
        state: { data: history, dataUpdatedAt: 1 } }],
    } } as unknown as PersistedClient
    expect(sanitizeSnapshot(snapshot).clientState.queries).toEqual([])
  })
})
