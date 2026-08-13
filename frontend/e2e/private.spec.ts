import type { Locator } from '@playwright/test'

import {
  expect,
  fixturePrivatePin,
  fixtureWrongPin,
  test,
} from './fixtures/tasks'

function relativeLuminance(hex: string): number {
  const value = hex.replace('#', '')
  const linear = [0, 2, 4].map((offset) => {
    const channel = Number.parseInt(value.slice(offset, offset + 2), 16) / 255
    return channel <= 0.03928
      ? channel / 12.92
      : Math.pow((channel + 0.055) / 1.055, 2.4)
  })
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
}

function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a)
  const lb = relativeLuminance(b)
  const [lighter, darker] = la >= lb ? [la, lb] : [lb, la]
  return (lighter + 0.05) / (darker + 0.05)
}

function rgbToHex(rgb: string): string {
  const match = rgb.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/)
  if (!match) return rgb
  return `#${[1, 2, 3]
    .map((index) => Number(match[index]).toString(16).padStart(2, '0'))
    .join('')}`
}

async function renderedControlContrast(
  locator: Locator,
): Promise<{ border: string; surface: string; ratio: number }> {
  const colors = await locator.evaluate((element) => {
    const border = getComputedStyle(element).borderTopColor
    let ancestor = element.parentElement
    while (ancestor) {
      const background = getComputedStyle(ancestor).backgroundColor
      if (background !== 'transparent' && background !== 'rgba(0, 0, 0, 0)') {
        return { border, surface: background }
      }
      ancestor = ancestor.parentElement
    }
    return { border, surface: getComputedStyle(document.body).backgroundColor }
  })
  const border = rgbToHex(colors.border)
  const surface = rgbToHex(colors.surface)
  return { border, surface, ratio: contrastRatio(border, surface) }
}

test('correct PIN opens private tasks and changes the badge', async ({ page, taskApi }) => {
  taskApi.privateUntil = null
  await page.goto('/')

  await expect(page.getByTestId('private-badge')).toContainText('đang khoá')
  await expect(page.getByText('Task riêng tư')).toHaveCount(0)

  await page.getByTestId('private-unlock-open').click()
  const inputContrast = await renderedControlContrast(page.getByTestId('private-pin-input'))
  expect(
    inputContrast.ratio,
    `private PIN input border ${inputContrast.border} vs dialog surface ${inputContrast.surface}`,
  ).toBeGreaterThanOrEqual(3)
  await page.getByTestId('private-pin-input').fill(fixturePrivatePin)
  await page.getByTestId('private-unlock-submit').click()

  await expect(page.getByTestId('private-badge')).toContainText('còn')
  await expect(page.getByText('Task riêng tư')).toBeVisible()
})

test('ten wrong PIN attempts produce throttle countdown and disable unlock', async ({
  page,
  taskApi,
}) => {
  taskApi.privateUntil = null
  await page.goto('/')
  await page.getByTestId('private-unlock-open').click()

  for (let attempt = 1; attempt <= 10; attempt += 1) {
    await page.getByTestId('private-pin-input').fill(fixtureWrongPin)
    await page.getByTestId('private-unlock-submit').click()
    if (attempt < 10) {
      await expect(page.getByTestId('private-error')).toContainText(
        `Còn ${10 - attempt} lần`,
      )
    }
  }

  await expect(page.getByTestId('private-badge')).toContainText(/Khoá tạm · còn [45]:[0-5][0-9]/)
  await expect(page.getByTestId('private-unlock-submit')).toBeDisabled()
  const badgeContrast = await renderedControlContrast(page.getByTestId('private-badge'))
  expect(
    badgeContrast.ratio,
    `throttled private badge border ${badgeContrast.border} vs page surface ${badgeContrast.surface}`,
  ).toBeGreaterThanOrEqual(3)
})

test('lock now removes private task responses before the locked refetch', async ({
  page,
}) => {
  await page.goto('/')
  await expect(page.getByText('Task riêng tư')).toBeVisible()

  await page.getByTestId('private-lock-now').click()

  await expect(page.getByTestId('private-badge')).toContainText('đang khoá')
  await expect(page.getByText('Task riêng tư')).toHaveCount(0)
})
