import assert from 'node:assert/strict'
import { test } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import { TaskForm } from '../src/TaskForm'

test('task form renders the complete edit surface with existing values', () => {
  const html = renderToStaticMarkup(
    <TaskForm
      initial={{
        title: 'Chuẩn bị họp',
        body_md: 'Mang tài liệu',
        priority: 'p1',
        due_precision: 'none',
        due_on: null,
        due_at: null,
        is_private: true,
      }}
      submitLabel="Lưu thay đổi"
      pending={false}
      onSubmit={() => undefined}
      onCancel={() => undefined}
    />,
  )

  assert.match(html, /Chuẩn bị họp/)
  assert.match(html, /Mang tài liệu/)
  assert.match(html, /data-selected-priority="p1">P1/)
  assert.match(html, /data-selected-due-precision="none">Chưa xếp lịch/)
  assert.match(html, /data-state="checked"/)
  assert.match(html, /Lưu thay đổi/)
  assert.match(html, /Huỷ/)
})

test('pending task form disables submit and exposes its progress label', () => {
  const html = renderToStaticMarkup(
    <TaskForm
      initial={{
        title: 'Không nhân đôi',
        body_md: null,
        priority: null,
        due_precision: 'none',
        due_on: null,
        due_at: null,
        is_private: false,
      }}
      submitLabel="Tạo task"
      pending
      onSubmit={() => undefined}
    />,
  )

  assert.match(html, /disabled=""/)
  assert.match(html, /Đang lưu…/)
})

test('new task form defaults to a date without rendering a time input', () => {
  const html = renderToStaticMarkup(
    <TaskForm
      submitLabel="Tạo task"
      pending={false}
      onSubmit={() => undefined}
    />,
  )

  assert.match(html, /data-selected-due-precision="date">Ngày/)
  assert.match(html, /type="date"/)
  assert.doesNotMatch(html, /type="time"/)
})
