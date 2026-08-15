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

type Rgba = { red: number; green: number; blue: number; alpha: number }

async function waitForFinalTransition(locator: Locator): Promise<void> {
  await locator.evaluate(async (element) => {
    const nextFrame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
    const milliseconds = (value: string) => {
      const parsed = Number.parseFloat(value)
      if (!Number.isFinite(parsed)) return 0
      return value.trim().endsWith('ms') ? parsed : parsed * 1000
    }

    // Let the browser apply the state change (focus/blur or badge variant) before
    // deriving the transition duration. The final frame keeps the read below out
    // of the last composited transition frame.
    await nextFrame()
    const style = getComputedStyle(element)
    const durations = style.transitionDuration.split(',').map(milliseconds)
    const delays = style.transitionDelay.split(',').map(milliseconds)
    const settleAfter = Math.max(
      0,
      ...durations.map((duration, index) => duration + delays[index % delays.length]),
    )
    if (settleAfter > 0) {
      await new Promise<void>((resolve) => window.setTimeout(resolve, settleAfter))
    }
    await nextFrame()
  })
}

function composite(foreground: Rgba, background: Rgba): Rgba {
  const alpha = foreground.alpha + background.alpha * (1 - foreground.alpha)
  if (alpha === 0) return { red: 0, green: 0, blue: 0, alpha: 0 }
  const channel = (front: number, back: number) =>
    (front * foreground.alpha + back * background.alpha * (1 - foreground.alpha)) / alpha
  return {
    red: channel(foreground.red, background.red),
    green: channel(foreground.green, background.green),
    blue: channel(foreground.blue, background.blue),
    alpha,
  }
}

function opaqueHex(color: Rgba): string {
  if (color.alpha < 1) throw new Error(`Expected opaque rendered color, got alpha ${color.alpha}`)
  return `#${[color.red, color.green, color.blue]
    .map((channel) => Math.round(channel).toString(16).padStart(2, '0'))
    .join('')}`
}

async function renderedControlContrast(
  locator: Locator,
): Promise<{
  border: string
  surface: string
  backdrop: string
  ratio: number
  backdropRatio: number
  rawSurface: string
}> {
  await waitForFinalTransition(locator)
  const colors = await locator.evaluate((element) => {
    const canvas = document.createElement('canvas')
    canvas.width = 1
    canvas.height = 1
    const context = canvas.getContext('2d', { colorSpace: 'srgb', willReadFrequently: true })
    if (!context) throw new Error('Unable to create sRGB canvas for contrast measurement')
    const renderedRgba = (color: string) => {
      context.clearRect(0, 0, 1, 1)
      context.fillStyle = color
      context.fillRect(0, 0, 1, 1)
      const [red, green, blue, alpha] = context.getImageData(0, 0, 1, 1).data
      return { red, green, blue, alpha: alpha / 255 }
    }
    const style = getComputedStyle(element)
    const backgrounds = [style.backgroundColor]
    let ancestor: Element | null = element.parentElement
    while (ancestor) {
      backgrounds.push(getComputedStyle(ancestor).backgroundColor)
      ancestor = ancestor.parentElement
    }
    return {
      border: renderedRgba(style.borderTopColor),
      backgrounds: backgrounds.map(renderedRgba),
      rawSurface: style.backgroundColor,
    }
  })

  // Tailwind v4's computed alpha color is `oklab(...)`, not necessarily
  // `rgba(...)`. The in-browser sRGB canvas above normalizes each CSS color
  // before this source-over composite from the outermost ancestor inward.
  const white: Rgba = { red: 255, green: 255, blue: 255, alpha: 1 }
  const backdrop = colors.backgrounds
    .slice(1)
    .reverse()
    .reduce((result, color) => composite(color, result), white)
  const surfaceColor = composite(colors.backgrounds[0], backdrop)
  // CSS backgrounds extend under borders by default, so an alpha border is
  // rendered over the same effective fill. Current controls use opaque borders.
  const borderColor = composite(colors.border, surfaceColor)
  const border = opaqueHex(borderColor)
  const surface = opaqueHex(surfaceColor)
  const backdropHex = opaqueHex(backdrop)
  return {
    border,
    surface,
    backdrop: backdropHex,
    ratio: contrastRatio(border, surface),
    backdropRatio: contrastRatio(border, backdropHex),
    rawSurface: colors.rawSurface,
  }
}

test('correct PIN opens private tasks and changes the badge', async ({ page, taskApi }) => {
  taskApi.privateUntil = null
  await page.goto('/')

  await expect(page.getByTestId('private-badge')).toContainText('đang khoá')
  await expect(page.getByText('Task riêng tư')).toHaveCount(0)

  await page.getByTestId('private-unlock-open').click()
  const pinInput = page.getByTestId('private-pin-input')
  await expect(pinInput).toBeFocused()
  const focusContrast = await renderedControlContrast(pinInput)
  expect(
    focusContrast.ratio,
    `private PIN input focus border ${focusContrast.border} vs dialog surface ${focusContrast.surface}`,
  ).toBeGreaterThanOrEqual(3)
  // Dialog autofocus gives this input the rose focus ring. Blur first so this
  // guardrail measures the normal `border-input` control boundary instead.
  await pinInput.blur()
  await expect(pinInput).not.toBeFocused()
  const inputContrast = await renderedControlContrast(pinInput)
  expect(
    inputContrast.ratio,
    `private PIN input normal border ${inputContrast.border} vs dialog surface ${inputContrast.surface}`,
  ).toBeGreaterThanOrEqual(3)
  await pinInput.fill(fixturePrivatePin)
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
    `throttled private badge border ${badgeContrast.border} vs rendered fill ${badgeContrast.surface} (${badgeContrast.rawSurface} over ${badgeContrast.backdrop}; backdrop ratio ${badgeContrast.backdropRatio.toFixed(2)})`,
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
