import { describe, expect, it } from 'vitest'

import {
  appendFutureReflection,
  deleteFutureReflection,
  formatNoteTime,
  notePayload,
  parseNoteBody,
  updateFutureReflection,
  sortNotes,
  fetchAllNotes,
  NotePageLimitError,
  type Note,
  type NoteFormState,
} from '@/note-ui'

describe('parseNoteBody', () => {
  it('splits base markdown and reflections cleanly', () => {
    const raw =
      '# Tiêu đề ghi chú\n\nNội dung chính.\n\n> 💬 **Lời nhắn từ tương lai** (14:30 · 25/08/2026):\n> Lời nhắn từ tương lai.\n\n---\n\n> 💬 **Lời nhắn từ tương lai** (15:00 · 25/08/2026):\n> Lời nhắn thứ hai.'
    const parsed = parseNoteBody(raw)
    expect(parsed.baseText).toBe('# Tiêu đề ghi chú\n\nNội dung chính.')
    expect(parsed.reflections).toHaveLength(2)
    expect(parsed.reflections[0]?.text).toBe('Lời nhắn từ tương lai.')
    expect(parsed.reflections[0]?.time).toBe('14:30 · 25/08/2026')
    expect(parsed.reflections[1]?.text).toBe('Lời nhắn thứ hai.')
  })

  it('handles body with only base markdown and no reflections', () => {
    const raw = 'Chỉ có nội dung chính.'
    const parsed = parseNoteBody(raw)
    expect(parsed.baseText).toBe('Chỉ có nội dung chính.')
    expect(parsed.reflections).toHaveLength(0)
  })

  it('handles null body', () => {
    const parsed = parseNoteBody(null)
    expect(parsed.baseText).toBe('')
    expect(parsed.reflections).toHaveLength(0)
  })
})

describe('notePayload', () => {
  it('trims title and body, preserving nulls for empty text', () => {
    const state: NoteFormState = {
      title: '  Tiêu đề  ',
      body: '  Nội dung  ',
      isPrivate: false,
    }
    const payload = notePayload(state)
    expect(payload.title).toBe('Tiêu đề')
    expect(payload.body_md).toBe('Nội dung')
    expect(payload.is_private).toBe(false)
  })

  it('returns null for blank title and body', () => {
    const state: NoteFormState = {
      title: '   ',
      body: '',
      isPrivate: true,
    }
    const payload = notePayload(state)
    expect(payload.title).toBeNull()
    expect(payload.body_md).toBeNull()
    expect(payload.is_private).toBe(true)
  })
})

describe('future reflection formatting', () => {
  it('formats current time in Vietnam timezone (HH:mm · DD/MM/YYYY)', () => {
    const formatted = formatNoteTime('2026-08-25T07:30:00Z')
    expect(formatted).toBe('14:30 · 25/08/2026')
  })

  it('appends a new reflection without losing base text', () => {
    const initial = 'Kế hoạch ban đầu.'
    const withReflection = appendFutureReflection(initial, 'Cần thêm mục A.', '2026-08-25T07:30:00Z')
    expect(withReflection).toContain('Kế hoạch ban đầu.')
    expect(withReflection).toContain('> 💬 **Lời nhắn từ tương lai** (14:30 · 25/08/2026):\n> Cần thêm mục A.')
  })

  it('updates an existing reflection at index', () => {
    const initial =
      'Kế hoạch ban đầu.\n\n---\n\n> 💬 **Lời nhắn từ tương lai** (14:30 · 25/08/2026):\n> Cần thêm mục A.\n\n---\n\n> 💬 **Lời nhắn từ tương lai** (15:00 · 25/08/2026):\n> Cần thêm mục B.'
    const updated = updateFutureReflection(initial, 0, 'Cần thêm mục A (đã sửa).')
    const parsed = parseNoteBody(updated)
    expect(parsed.reflections[0]?.text).toBe('Cần thêm mục A (đã sửa).')
    expect(parsed.reflections[1]?.text).toBe('Cần thêm mục B.')
  })

  it('deletes a reflection at index', () => {
    const initial =
      'Kế hoạch ban đầu.\n\n---\n\n> 💬 **Lời nhắn từ tương lai** (14:30 · 25/08/2026):\n> Cần thêm mục A.\n\n---\n\n> 💬 **Lời nhắn từ tương lai** (15:00 · 25/08/2026):\n> Cần thêm mục B.'
    const updated = deleteFutureReflection(initial, 0)
    const parsed = parseNoteBody(updated)
    expect(parsed.reflections).toHaveLength(1)
    expect(parsed.reflections[0]?.text).toBe('Cần thêm mục B.')

    const afterDelete = parseNoteBody(deleteFutureReflection(updated, 0))
    expect(afterDelete.reflections).toHaveLength(0)
    expect(afterDelete.baseText).toBe('Kế hoạch ban đầu.')
  })
})

function mockNote(overrides: Partial<Note>): Note {
  return {
    id: 'note-' + Math.random().toString(36).slice(2),
    title: 'Tiêu đề',
    body_md: null,
    is_private: false,
    pinned: false,
    items: [],
    created_at: '2026-08-01T10:00:00Z',
    updated_at: null,
    ...overrides,
  }
}

describe('note sorting rules', () => {
  it('sorts by alphabet using Vietnamese collation (A-Z) with uppercase, accents, numbers, null titles', () => {
    const notes: Note[] = [
      mockNote({ id: '1', title: 'Đà Nẵng' }),
      mockNote({ id: '2', title: 'An Giang' }),
      mockNote({ id: '3', title: 'Bình Dương' }),
      mockNote({ id: '4', title: 'Đắc Lắk' }),
      mockNote({ id: '5', title: null }), // "Không tiêu đề" (K)
      mockNote({ id: '6', title: '123 Đề mục số' }),
      mockNote({ id: '7', title: 'Áo dài' }),
    ]
    const sorted = sortNotes(notes, 'alphabet')
    expect(sorted.map((n) => n.title)).toEqual([
      '123 Đề mục số',
      'An Giang',
      'Áo dài',
      'Bình Dương',
      'Đà Nẵng',
      'Đắc Lắk',
      null, // "Không tiêu đề"
    ])
  })

  it('sorts by created_at (newest first)', () => {
    const notes: Note[] = [
      mockNote({ id: '1', title: 'Oldest', created_at: '2026-08-01T10:00:00Z' }),
      mockNote({ id: '2', title: 'Newest', created_at: '2026-08-03T10:00:00Z' }),
      mockNote({ id: '3', title: 'Middle', created_at: '2026-08-02T10:00:00Z' }),
    ]
    const sorted = sortNotes(notes, 'created')
    expect(sorted.map((n) => n.title)).toEqual(['Newest', 'Middle', 'Oldest'])
  })

  it('sorts by updated_at (newest first, fallback to created_at)', () => {
    const notes: Note[] = [
      mockNote({ id: '1', title: 'Created recently, not updated', created_at: '2026-08-05T10:00:00Z', updated_at: null }),
      mockNote({ id: '2', title: 'Old note updated very recently', created_at: '2026-08-01T10:00:00Z', updated_at: '2026-08-06T10:00:00Z' }),
      mockNote({ id: '3', title: 'Oldest note', created_at: '2026-08-01T08:00:00Z', updated_at: '2026-08-02T10:00:00Z' }),
    ]
    const sorted = sortNotes(notes, 'updated')
    expect(sorted.map((n) => n.title)).toEqual([
      'Old note updated very recently',
      'Created recently, not updated',
      'Oldest note',
    ])
  })

  it('pinned partition always wins over sort mode and tie-breaker applies cleanly', () => {
    const notes: Note[] = [
      mockNote({ id: '1', title: 'Zebra (Normal)', pinned: false }),
      mockNote({ id: '2', title: 'Banana (Pinned)', pinned: true }),
      mockNote({ id: '3', title: 'Apple (Normal)', pinned: false }),
      mockNote({ id: '4', title: 'Cherry (Pinned)', pinned: true }),
    ]
    const sorted = sortNotes(notes, 'alphabet')
    expect(sorted.map((n) => n.title)).toEqual([
      'Banana (Pinned)',
      'Cherry (Pinned)',
      'Apple (Normal)',
      'Zebra (Normal)',
    ])
  })
})

describe('fetchAllNotes pagination & safety cap', () => {
 it('fetches 101 notes across page boundary and participates in sort', async () => {
   const page1Notes = Array.from({ length: 100 }, (_, i) => mockNote({ id: `p1-${i}`, title: `Note ${i}` }))
   const page2Notes = [mockNote({ id: 'p2-0', title: 'AAA Note' })]

   const fetchMock = async (_limit: number, offset: number) => {
     if (offset === 0) return { items: page1Notes }
     if (offset === 100) return { items: page2Notes }
     return { items: [] }
   }

   const all = await fetchAllNotes(fetchMock)
   expect(all.length).toBe(101)
   const sorted = sortNotes(all, 'alphabet')
   expect(sorted[0]?.title).toBe('AAA Note')
 })

  it('deduplicates partial overlap across pages and continues pagination to collect unique items', async () => {
    // Page 1: IDs 0..99
    const page1 = Array.from({ length: 100 }, (_, i) => mockNote({ id: `id-${i}`, title: `Title ${i}` }))
    // Page 2: IDs 90..189 (10 overlap items [90..99] + 90 new items [100..189])
    const page2 = [
      ...Array.from({ length: 10 }, (_, i) => mockNote({ id: `id-${90 + i}`, title: `Title ${90 + i}` })),
      ...Array.from({ length: 90 }, (_, i) => mockNote({ id: `id-${100 + i}`, title: `Title ${100 + i}` })),
    ]
    // Page 3: 5 short items
    const page3 = Array.from({ length: 5 }, (_, i) => mockNote({ id: `id-p3-${i}`, title: `P3 ${i}` }))

    const fetchMock = async (_limit: number, offset: number) => {
      if (offset === 0) return { items: page1 }
      if (offset === 100) return { items: page2 }
      if (offset === 200) return { items: page3 }
      return { items: [] }
    }

    const all = await fetchAllNotes(fetchMock)
    // 100 from p1 + 90 unique from p2 + 5 from p3 = 195 unique notes
    expect(all.length).toBe(195)
    expect(new Set(all.map((n) => n.id)).size).toBe(195)
  })

  it('sorts notes cleanly across page boundaries when partial overlap is deduplicated', async () => {
    const page1 = [
      mockNote({ id: 'p1-1', title: 'Zebra Note', created_at: '2026-08-01T10:00:00Z' }),
      ...Array.from({ length: 99 }, (_, i) => mockNote({ id: `fill-${i}`, title: `Middle ${i}` })),
    ]
    // Page 2 has overlap on fill-98 and an 'Alpha Note' that must sort first
    const page2 = [
      mockNote({ id: 'fill-98', title: 'Middle 98' }),
      mockNote({ id: 'p2-1', title: 'Alpha Note', created_at: '2026-08-05T10:00:00Z' }),
    ]

    const fetchMock = async (_limit: number, offset: number) => {
      if (offset === 0) return { items: page1 }
      if (offset === 100) return { items: page2 }
      return { items: [] }
    }

    const all = await fetchAllNotes(fetchMock)
    expect(all.length).toBe(101)
    const sorted = sortNotes(all, 'alphabet')
    expect(sorted[0]?.title).toBe('Alpha Note')
    expect(sorted[sorted.length - 1]?.title).toBe('Zebra Note')
  })

  it('throws NotePageLimitError when full repeat page returns no new unique IDs (offset not progressing)', async () => {
    const page1 = Array.from({ length: 100 }, (_, i) => mockNote({ id: `id-${i}` }))
    const page2 = Array.from({ length: 100 }, (_, i) => mockNote({ id: `id-${i}` })) // identical full page

    const fetchMock = async (_limit: number, offset: number) => {
      if (offset === 0) return { items: page1 }
      if (offset === 100) return { items: page2 }
      return { items: [] }
    }

    await expect(fetchAllNotes(fetchMock)).rejects.toThrow(NotePageLimitError)
  })

  it('throws NotePageLimitError when repeated fingerprint is detected', async () => {
    const samePage = Array.from({ length: 100 }, (_, i) => mockNote({ id: `page-item-${i}` }))
    const fetchMock = async () => ({ items: samePage })

    await expect(fetchAllNotes(fetchMock)).rejects.toThrow(NotePageLimitError)
  })

  it('allows exactly 2000 notes when probe at offset 2000 returns empty', async () => {
    const fetchMock = async (_limit: number, offset: number) => {
      const pageIdx = offset / 100
      if (pageIdx < 20) {
        return {
          items: Array.from({ length: 100 }, (_, i) => mockNote({ id: `p${pageIdx}-${i}` })),
        }
      }
      return { items: [] }
    }

    const all = await fetchAllNotes(fetchMock)
    expect(all.length).toBe(2000)
  })

  it('throws NotePageLimitError when notes exceed 2000 cap (2001 notes probe non-empty)', async () => {
    const fetchMock = async (_limit: number, offset: number) => {
      const pageIdx = offset / 100
      if (pageIdx < 20) {
        return {
          items: Array.from({ length: 100 }, (_, i) => mockNote({ id: `p${pageIdx}-${i}` })),
        }
      }
      // 21st page probe returns 1 item (2001st note)
      return { items: [mockNote({ id: 'note-2001' })] }
    }

    await expect(fetchAllNotes(fetchMock)).rejects.toThrow(NotePageLimitError)
  })

  it('throws NotePageLimitError when an API page returns more than 100 items (oversized page)', async () => {
    const oversizedPage = Array.from({ length: 105 }, (_, i) => mockNote({ id: `over-${i}` }))
    const fetchMock = async () => ({ items: oversizedPage })

    await expect(fetchAllNotes(fetchMock)).rejects.toThrow(NotePageLimitError)
  })

  it('terminates normally on a short page (<100 items) and accepts exact unique IDs', async () => {
    const shortPage = Array.from({ length: 42 }, (_, i) => mockNote({ id: `short-${i}` }))
    const fetchMock = async (_limit: number, offset: number) => {
      if (offset === 0) return { items: shortPage }
      return { items: [] }
    }

    const notes = await fetchAllNotes(fetchMock)
    expect(notes.length).toBe(42)
  })
})
