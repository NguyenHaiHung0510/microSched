import assert from 'node:assert/strict'
import test from 'node:test'
import { renderToStaticMarkup } from 'react-dom/server'

import { TaskForm } from '../src/TaskForm.js'

test('task form renders the complete edit surface with existing values', () => {
  const html = renderToStaticMarkup(
    <TaskForm
      initial={{
        title: 'Chuẩn bị họp',
        body_md: 'Mang tài liệu',
        priority: 'p1',
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
  assert.match(html, /P1 — cao/)
  assert.match(html, /checked=""/)
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
