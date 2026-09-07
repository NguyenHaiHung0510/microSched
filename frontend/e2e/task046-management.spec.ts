import { expect, test } from './fixtures/tracker'

test('Task046 tracker management keeps long names and controls in separate mobile rows', async ({ page, trackerApi }) => {
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
