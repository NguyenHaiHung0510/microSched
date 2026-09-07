import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { expect, test } from './fixtures/tracker'

test('Task046 tracker management keeps long names and controls in separate mobile rows', async ({ page, trackerApi }, info) => {
  const longGroup = 'Nhóm theo dõi sức khoẻ, học tập và các thói quen cần ghi nhận rất dài'
  const longTracker = 'Tracker có tên dài để kiểm tra hàng thao tác vẫn chạm được ở màn hình điện thoại'
  trackerApi.groups = [{ id: 'long-group', name: longGroup, kind: 'health', tracker_count: 1 }]
  trackerApi.trackers = [{ ...trackerApi.trackers[0], id: 'long-tracker', name: longTracker, group_id: 'long-group', is_private: true }]
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Theo dõi' }).click()
  const management = page.getByTestId('tracker-management')
  const row = management.getByTestId('tracker-management-row')
  await expect(row).toHaveCount(1)
  await expect(row).toContainText(longTracker)
  const groupTitle = management.getByTestId('tracker-group-title')
  expect(await groupTitle.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  const geometry = await row.evaluate((element) => {
    const controls = [
      element.querySelector<HTMLElement>('label'),
      element.querySelector<HTMLElement>('[data-testid="tracker-edit"]'),
      element.querySelector<HTMLElement>('[data-testid="tracker-archive"]'),
    ].filter((control): control is HTMLElement => Boolean(control))
    const boxes = controls.map((control) => control.getBoundingClientRect())
    return {
      noHorizontalOverflow: document.documentElement.scrollWidth <= window.innerWidth,
      controls: boxes.map((box) => ({ left: box.left, right: box.right, top: box.top, bottom: box.bottom, width: box.width, height: box.height })),
    }
  })
  if (process.env.CAPTURE_UI_046 === '1') {
    await management.scrollIntoViewIfNeeded()
    const directory = path.resolve('../output/task-046/screenshots')
    mkdirSync(directory, { recursive: true })
    const file = `${info.project.name}-management-mobile.png`
    const bytes = await page.screenshot({ path: path.join(directory, file), animations: 'disabled' })
    writeFileSync(path.join(directory, `${info.project.name}-management-mobile.json`), JSON.stringify({ file,
      head: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), viewport: page.viewportSize(), capturedAt: new Date().toISOString(),
      md5: createHash('md5').update(bytes).digest('hex'), sha256: createHash('sha256').update(bytes).digest('hex'),
    }, null, 2))
  }
  expect(geometry.noHorizontalOverflow).toBe(true)
  expect(geometry.controls).toHaveLength(3)
  for (const control of geometry.controls) {
    expect(control.width).toBeGreaterThanOrEqual(44)
    expect(control.height).toBeGreaterThanOrEqual(44)
  }
  for (let index = 1; index < geometry.controls.length; index += 1) {
    expect(geometry.controls[index].left - geometry.controls[index - 1].right).toBeGreaterThanOrEqual(8)
  }
})
