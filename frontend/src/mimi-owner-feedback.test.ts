import { expect, test } from 'vitest'
import { feedbackComment, feedbackFieldOverflow } from './mimi-owner-feedback'
import { clampMimiRail, fitMimiRails, mimiRailMaximum } from './mimi-layout'

test('positive one-tap maps to an ordinary nonempty comment without inventing API fields', () => {
  expect(feedbackComment('positive', [], '')).toBe('Phản hồi tích cực: Hữu ích.')
})
test('negative feedback retains chosen reasons and exact issue in the existing comment', () => {
  expect(feedbackComment('negative', ['Thiếu ngữ cảnh', 'Khó hiểu'], 'Mimi bỏ mất checklist.')).toBe('Phản hồi chưa tốt.\nLý do: Thiếu ngữ cảnh, Khó hiểu.\nMimi bỏ mất checklist.')
  expect(() => feedbackComment('negative', ['Khác'], '   ')).toThrow('requires an issue')
  expect(() => feedbackComment('negative', [], 'x'.repeat(8001))).toThrow('exceeds8000')
  expect(feedbackComment('negative', [], 'x'.repeat(8000))).toContain('x'.repeat(8000))
})

test('positive supplement allows exactly8000 Unicode codepoints with all reasons below the unchanged API limit', () => {
  const reasons = ['Rõ ràng', 'Đúng ý', 'Hữu ích', 'Nhanh', 'Dễ hiểu', 'Khác']
  const issue = '🌸'.repeat(7999) + 'ệ'
  const comment = feedbackComment('positive', reasons, issue)
  expect(comment).toContain(issue)
  expect(Array.from(comment).length).toBeLessThanOrEqual(10000)
  for (const reason of reasons) expect(comment).toContain(reason)
  expect(() => feedbackComment('positive', reasons, issue + 'x')).toThrow('exceeds8000')
  expect(() => feedbackComment('negative', reasons, issue)).not.toThrow()
  expect(() => feedbackComment('negative', [], issue + 'x')).toThrow('exceeds8000')
  expect(feedbackFieldOverflow(issue)).toBe(false)
  expect(feedbackFieldOverflow(issue + 'x')).toBe(true)
})
test('normal desktop allows640px on either rail and preserves existing defaults/minimum', () => {
  expect(fitMimiRails(200, 220, 1490, true, true)).toEqual({ left: 200, right: 220 })
  expect(clampMimiRail(640, 1490, 220)).toBe(640)
  expect(clampMimiRail(640, 1490, 200)).toBe(640)
  expect(clampMimiRail(0, 1490, 220)).toBe(160)
})
test('viewport contraction fits stored wide preferences; active resize keeps other width and center reserve', () => {
  const fitted = fitMimiRails(640, 640, 1000, true, true)
  expect(fitted.left + fitted.right).toBe(720)
  expect(fitted.left).toBeGreaterThanOrEqual(160)
  expect(fitted.right).toBeGreaterThanOrEqual(160)
  expect(mimiRailMaximum(1000, 400)).toBe(320)
  expect(fitMimiRails(640, 640, 1490, true, false)).toEqual({ left: 640, right: 44 })
})
