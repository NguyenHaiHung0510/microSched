import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { test, expect } from './fixtures/tracker'

test('long capture names wrap inside their own target, separate from backdate controls', async ({ page, trackerApi }, info) => {
  const template = trackerApi.trackers[0]
  trackerApi.groups = [{ id: 'capture-group-046', name: 'Nhóm ghi nhanh với tên tiếng Việt rất dài ' + 'Ế'.repeat(70), kind: 'health', color: null, position: 0, tracker_count: 3 }]
  trackerApi.trackers = [
    'Theo dõi việc ghi chép sau buổi học và đọc lại những điều quan trọng',
    'X'.repeat(70),
    'Ghi nhanh',
  ].map((name, index) => ({ ...template, id: `capture-046-${index}`, name, group_id: 'capture-group-046', is_private: index === 1, input_mode: 'event', reminder_time: null }))
  await page.goto('/')
  await page.getByRole('tab', { name: 'Theo dõi' }).click()
  const cards = page.getByTestId('tracker-card')
  await expect(cards).toHaveCount(3)
  for (const card of await cards.all()) {
    const geometry = await card.evaluate(el => {
      const capture = el.querySelector('[data-testid="tracker-button"]')!, menu = el.querySelector('[data-testid="tracker-backdate"]')!, name = el.querySelector('[data-testid="tracker-capture-name"]')!
      const a=capture.getBoundingClientRect(), b=menu.getBoundingClientRect(), c=el.getBoundingClientRect(), n=name.getBoundingClientRect()
      return { gap: b.left-a.right, captureWidth: a.width, captureHeight: a.height, menuWidth: b.width, menuHeight: b.height,
        contained: a.left>=c.left && b.right<=c.right && n.right<=a.right, wraps: getComputedStyle(capture).whiteSpace, nameWidth: name.clientWidth, nameScroll: name.scrollWidth }
    })
    expect(geometry.gap).toBeGreaterThanOrEqual(8)
    expect(geometry.captureWidth).toBeGreaterThanOrEqual(44)
    expect(geometry.captureHeight).toBeGreaterThanOrEqual(44)
    expect(geometry.menuWidth).toBeGreaterThanOrEqual(44)
    expect(geometry.menuHeight).toBeGreaterThanOrEqual(44)
    expect(geometry.contained).toBe(true)
    expect(geometry.wraps).toBe('normal')
    expect(geometry.nameScroll).toBeLessThanOrEqual(geometry.nameWidth)
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  const first = cards.first()
  const count = trackerApi.entries.length
  await first.getByTestId('tracker-backdate').click()
  await expect(page.getByTestId('tracker-backdate-dialog')).toBeVisible()
  expect(trackerApi.entries).toHaveLength(count)
  await page.keyboard.press('Escape')
  await first.getByTestId('tracker-button').click()
  await expect.poll(() => trackerApi.entries.length).toBe(count + 1)
  if (process.env.CAPTURE_UI_046 === '1') {
    await first.scrollIntoViewIfNeeded()
    const directory = path.resolve('../output/task-046/screenshots')
    mkdirSync(directory, { recursive: true })
    const file = `${info.project.name}-capture-long-names.png`
    const bytes = await page.screenshot({ path: path.join(directory, file), animations: 'disabled' })
    writeFileSync(path.join(directory, `${info.project.name}-capture-long-names.json`), JSON.stringify({ file,
      head: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), viewport: page.viewportSize(), capturedAt: new Date().toISOString(),
      md5: createHash('md5').update(bytes).digest('hex'), sha256: createHash('sha256').update(bytes).digest('hex'),
    }, null, 2))
  }
})
