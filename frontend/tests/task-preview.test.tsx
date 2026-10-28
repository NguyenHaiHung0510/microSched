import { expect, test } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { TaskPreviewContent, type TaskPreviewData } from '../src/TaskPreview'
import { mergeDayChips, tasksByDueDay, type CalendarTask } from '../src/calendar-scroll'

const task: TaskPreviewData = { id: 'synthetic', due_precision: 'datetime', due_on: null, due_at: '2026-10-19T17:30:00Z', priority: 'p1', body_md: 'Nội dung đầy đủ\n' + 'Đ'.repeat(90),
  items: Array.from({ length: 8 }, (_, index) => ({ id: `item-${index}`, content: `Mục ${index}`, is_completed: index < 3 })) }

test('shared preview retains all text/items and honest status without title/footer or interactive checkboxes', () => {
  const html = renderToStaticMarkup(<TaskPreviewContent task={task} />)
  expect(html).toContain('20/10/2026')
  expect(html).toContain('00:30')
  expect(html).toContain('Ưu tiên cao')
  expect(html).toContain('Checklist · 3/8 đã xong')
  expect(html).toContain('Đ'.repeat(90))
  expect(html).toContain('Mục 7')
  expect(html).not.toContain('role="checkbox"')
  expect(html).not.toContain('<button')
  expect(html).not.toContain('Nhấp')
  expect(html).not.toContain('<h')
})

test('empty body/list omit sections and date-only remains a Vietnam calendar date', () => {
  const html = renderToStaticMarkup(<TaskPreviewContent task={{ id: 'empty', body_md: '  ', items: [], due_precision: 'date', due_on: '2024-02-29', due_at: null }} />)
  expect(html).toContain('29/02/2024')
  expect(html).not.toContain('task-preview-body')
  expect(html).not.toContain('task-preview-checklist')
})

test('calendar grouping and chip projection preserve rich historical task data', () => {
  const calendarTask = { ...task, title: 'Task lịch sử', status: 'open', created_at: null, updated_at: null, is_private: false, pinned: false } as CalendarTask
  const days = tasksByDueDay([calendarTask])
  const chip = mergeDayChips([], days.get('2026-10-20')!, 4).chips[0]
  expect(chip.kind).toBe('task')
  if (chip.kind !== 'task') throw new Error('Expected task')
  expect(chip.task.body_md).toBe(task.body_md)
  expect(chip.task.items).toEqual(task.items)
  expect(chip.task.priority).toBe('p1')
})
