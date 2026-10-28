import { expect, test } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MimiMessageText } from './MimiMessageText'

test('assistant prose renders Vietnamese emphasis and a readable list', () => {
  const html = renderToStaticMarkup(<MimiMessageText text={'**Đang mở:** 6\n\n- Ôn bài\n- Viết báo cáo'} />)
  expect(html).toContain('<strong>Đang mở:</strong>')
  expect(html).toContain('<ul>')
})

test('untrusted markdown cannot run HTML or automatically load remote images', () => {
  const html = renderToStaticMarkup(<MimiMessageText text={'<script>alert(1)</script>\n\n![pixel](https://example.invalid/pixel?data=synthetic)\n\n[x](javascript:alert(1))'} />)
  expect(html).not.toContain('<script')
  expect(html).not.toContain('<img')
  expect(html).not.toContain('href="javascript:')
  expect(html).toContain('[Ảnh: pixel]')
})
