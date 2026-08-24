import assert from 'node:assert/strict'
import { test } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import { NoteForm } from '../src/NoteForm'

test('note form renders edit surface with pinned and private states', () => {
  const html = renderToStaticMarkup(
    <NoteForm
      initial={{
        title: 'Ý tưởng tương lai',
        body_md: 'Ghi chú ban đầu',
        is_private: true,
        pinned: true,
      }}
      submitLabel="Lưu thay đổi"
      pending={false}
      onSubmit={() => undefined}
      onCancel={() => undefined}
    />,
  )

  assert.match(html, /Ý tưởng tương lai/)
  assert.match(html, /Ghi chú ban đầu/)
  assert.match(html, /Riêng tư/)
  assert.match(html, /Ghim lên đầu/)
  assert.match(html, /Lưu thay đổi/)
  assert.match(html, /Huỷ/)
})

test('pending note form disables submit and shows progress label', () => {
  const html = renderToStaticMarkup(
    <NoteForm
      initial={{
        title: 'Note chờ',
        body_md: null,
        is_private: false,
      }}
      submitLabel="Tạo ghi chú"
      pending
      onSubmit={() => undefined}
    />,
  )

  assert.match(html, /disabled=""/)
  assert.match(html, /Đang lưu…/)
})
