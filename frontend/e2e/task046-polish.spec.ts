import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { test, expect } from './fixtures/tasks'

async function capture(page: import('@playwright/test').Page, name: string, project: string) {
  if (process.env.CAPTURE_UI_046 !== '1') return
  const directory = path.resolve('../output/task-046/screenshots')
  mkdirSync(directory, { recursive: true })
  await page.evaluate(() => document.fonts.ready)
  const file = `${project}-${name}.png`
  const bytes = await page.screenshot({ path: path.join(directory, file), animations: 'disabled' })
  writeFileSync(path.join(directory, `${project}-${name}.json`), JSON.stringify({
    file, head: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    viewport: page.viewportSize(), capturedAt: new Date().toISOString(),
    md5: createHash('md5').update(bytes).digest('hex'), sha256: createHash('sha256').update(bytes).digest('hex'),
  }, null, 2))
}

test('reflection is distinct from private note in card and detail, with readable text', async ({ page, taskApi }, info) => {
  const reflection = '\n\n> 💬 **Lời nhắn từ tương lai** (10:00 · 07/09/2026):\n> Ghi lại điều đã học và tiếp tục hoàn thiện từng ngày.'
  const notes = [{ id: 'note046-private', title: 'Ghi chú riêng tư mô phỏng', is_private: true },
    { id: 'note046-standard', title: 'Ghi chú thường mô phỏng', is_private: false }].map(note => ({
    ...note, body_md: 'Nội dung mô phỏng để so sánh hai ý nghĩa hiển thị.' + reflection,
    pinned: false, items: [], created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-07T00:00:00Z',
  }))
  await page.route('**/api/notes**', route => route.fulfill({ json: { items: notes.filter(note => !note.is_private || Boolean(taskApi.privateUntil)) } }))
  await page.goto('/')
  await page.getByRole('tab', { name: 'Ghi chú' }).click()
  const card = page.locator('[data-testid="note-card"][data-note-id="note046-private"]')
  await expect(card.getByTestId('note-private-badge-card')).toBeVisible()
  const reflectionBox = card.getByTestId('note-reflection-box')
  await expect(reflectionBox).toBeVisible()
  const geometry = await card.evaluate(element => {
    const box = element.querySelector('[data-testid="note-reflection-box"]')!
    const cs = getComputedStyle(element), rs = getComputedStyle(box)
    const paragraph = box.querySelector('p')!
    const rgb = (s: string) => (s.match(/[\d.]+/g) ?? []).slice(0,3).map(Number)
    const lum = (values: number[]) => values.map(v => { const c = v/255; return c <= .04045 ? c/12.92 : ((c+.055)/1.055)**2.4 }).reduce((s,v,i) => s+v*[.2126,.7152,.0722][i],0)
    const a=lum(rgb(rs.backgroundColor)), b=lum(rgb(getComputedStyle(paragraph).color))
    return { cardBg: cs.backgroundColor, reflectionBg: rs.backgroundColor, cardEdge: parseFloat(cs.borderLeftWidth), reflectionEdge: parseFloat(rs.borderLeftWidth),
      contrast: (Math.max(a,b)+.05)/(Math.min(a,b)+.05), font: parseFloat(getComputedStyle(paragraph).fontSize),
      contained: box.getBoundingClientRect().right <= element.getBoundingClientRect().right }
  })
  expect(geometry.cardBg).not.toBe(geometry.reflectionBg)
  expect(geometry.cardEdge).toBe(4)
  expect(geometry.reflectionEdge).toBe(1)
  expect(geometry.contrast).toBeGreaterThanOrEqual(4.5)
  expect(geometry.font).toBeGreaterThanOrEqual(12)
  expect(geometry.contained).toBe(true)
  await test.info().attach('reflection-measurements', { body: JSON.stringify(geometry), contentType: 'application/json' })
  await capture(page, 'reflection-private-card', info.project.name)
  await card.getByTestId('note-title').click()
  const detail = page.getByTestId('note-reflection-box-detail')
  await expect(detail).toBeVisible()
  expect(await detail.evaluate(el => getComputedStyle(el).backgroundColor)).toBe(geometry.reflectionBg)
  await capture(page, 'reflection-detail', info.project.name)
  await page.keyboard.press('Escape')
  await page.getByTestId('private-lock-now').click()
  await expect(card).toHaveCount(0)
  await expect(page.getByTestId('note-card')).toHaveCount(1)
})

test('calendar scrollbar stays inset inside a separate frame and scrolling still works', async ({ page }, info) => {
  await page.route('**/api/calendar/**', route => route.fulfill({ json: { items: [] } }))
  await page.goto('/')
  await page.getByRole('tab', { name: 'Lịch' }).click()
  const scroll = page.getByTestId('calendar-scroll-container')
  await expect(scroll).toBeVisible()
  const geometry = await scroll.evaluate(el => {
    const frame = el.parentElement!, a = el.getBoundingClientRect(), b = frame.getBoundingClientRect()
    return { left: a.left-b.left, right: b.right-a.right, top: a.top-b.top, frameOverflow: getComputedStyle(frame).overflow,
      scrollable: el.scrollHeight > el.clientHeight, gutter: getComputedStyle(el).scrollbarGutter }
  })
  expect(geometry.left).toBeGreaterThanOrEqual(4)
  expect(geometry.right).toBeGreaterThanOrEqual(4)
  expect(geometry.top).toBeGreaterThanOrEqual(4)
  expect(geometry.frameOverflow).toBe('hidden')
  expect(geometry.scrollable).toBe(true)
  expect(geometry.gutter).toBe('stable')
  const before = await scroll.evaluate(el => el.scrollTop)
  await scroll.evaluate(el => { el.scrollTop += 120 })
  await expect.poll(() => scroll.evaluate(el => el.scrollTop)).toBeGreaterThan(before)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await test.info().attach('scrollbar-measurements', { body: JSON.stringify(geometry), contentType: 'application/json' })
  await capture(page, 'calendar-scroll-frame', info.project.name)
})
