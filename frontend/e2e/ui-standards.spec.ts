import { expect } from '@playwright/test'

import { test } from './fixtures/tracker'

/**
 * F15 (spec 011d §4.4) UI standards: touch targets and non-text contrast,
 * measured with real numbers instead of eyeballed estimates.
 *
 * Both tests must FAIL on the pre-fix code: tab nav was h-9 (36px) and
 * `--border` was #e8dedf (~1.33:1 on the app background).
 */

function relativeLuminance(hex: string): number {
  const value = hex.replace('#', '')
  const linear = [0, 2, 4].map((offset) => {
    const channel = parseInt(value.slice(offset, offset + 2), 16) / 255
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

test('F15: tab nav touch targets are >= 44px and never overflow 390px', async ({
  page,
}) => {
  await page.goto('/')

  const tabs = page.getByRole('tab')
  await expect(tabs).toHaveCount(4)
  const heights: number[] = []
  for (let index = 0; index < 4; index += 1) {
    const box = await tabs.nth(index).boundingBox()
    expect(box, `tab #${index} must be visible`).not.toBeNull()
    heights.push(box!.height)
  }
  for (const height of heights) {
    expect(height, `tab height ${height}px must be >= 44px (Apple HIG)`).toBeGreaterThanOrEqual(44)
  }

  const overflow = await page.evaluate(() => {
    const el = document.scrollingElement ?? document.documentElement
    return { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }
  })
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth)
})

test('F15: dialog Close hit target is >= 44px', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('tab', { name: 'Theo dõi' }).click()
  await page.getByRole('button', { name: 'Tracker mới' }).click()
  const close = page.getByRole('button', { name: 'Đóng' })
  await expect(close).toBeVisible()
  const box = await close.boundingBox()
  expect(box).not.toBeNull()
  expect(box!.width).toBeGreaterThanOrEqual(44)
  expect(box!.height).toBeGreaterThanOrEqual(44)
})

test('011b: registers this device before saving the first tracker reminder', async ({
  page,
  trackerApi,
}) => {
  let releaseSubscribe: (() => void) | undefined
  const subscribeGate = new Promise<void>((resolve) => {
    releaseSubscribe = resolve
  })
  let subscribeStarted = false

  await page.addInitScript(() => {
    Object.defineProperty(window, 'Notification', {
      configurable: true,
      value: { requestPermission: async () => 'granted' },
    })
    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: {
        ready: Promise.resolve({
          pushManager: {
            subscribe: async () => ({
              endpoint: 'https://fcm.googleapis.com/fcm/send/e2e-device',
              toJSON: () => ({ keys: { p256dh: 'p256dh-value', auth: 'auth-value' } }),
            }),
          },
        }),
      },
    })
  })
  await page.route('**/api/push/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/push/vapid-public-key') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ public_key: 'BEl6JzoAAAAA' }),
      })
      return
    }
    if (path === '/api/push/subscribe') {
      subscribeStarted = true
      await subscribeGate
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ id: 'device-001', status: 'created' }),
      })
      return
    }
    await route.fallback()
  })

  await page.goto('/')
  await page.getByRole('tab', { name: 'Theo dõi' }).click()
  await page.getByRole('button', { name: 'Sửa Hút thuốc' }).click()
  await page.getByTestId('tracker-reminder-enabled').click()
  await page.getByTestId('tracker-reminder-time').fill('08:30')
  await page.getByRole('button', { name: 'Lưu thay đổi' }).click()

  await expect.poll(() => subscribeStarted).toBe(true)
  expect(trackerApi.count('PATCH', '/api/tracker/trackers/tracker-001')).toBe(0)
  releaseSubscribe?.()
  await expect
    .poll(() => trackerApi.count('PATCH', '/api/tracker/trackers/tracker-001'))
    .toBe(1)
})

test('F15: --border token and rendered outline borders keep non-text contrast >= 3:1', async ({
  page,
}) => {
  await page.goto('/')

  const token = await page.evaluate(() => {
    const style = getComputedStyle(document.documentElement)
    return {
      border: style.getPropertyValue('--border').trim(),
      background: style.getPropertyValue('--background').trim(),
    }
  })
  expect(token.border).toMatch(/^#[0-9a-f]{6}$/i)
  expect(token.background).toMatch(/^#[0-9a-f]{6}$/i)
  const tokenRatio = contrastRatio(token.border, token.background)
  expect(tokenRatio, `--border ${token.border} vs ${token.background}`).toBeGreaterThanOrEqual(3)

  // Rendered outline buttons: their visible border is the control's boundary,
  // so it must hold >= 3:1 against the button's own background (light mode).
  const borders = await page.evaluate(() => {
    const rows: Array<{ border: string; background: string }> = []
    for (const el of document.querySelectorAll<HTMLElement>(
      '[data-slot="button"][data-variant="outline"]',
    )) {
      const style = getComputedStyle(el)
      const background = style.backgroundColor
      if (background === 'transparent' || background.startsWith('rgba(0, 0, 0, 0)')) continue
      rows.push({ border: style.borderTopColor, background })
    }
    return rows
  })
  expect(borders.length).toBeGreaterThan(0)
  for (const row of borders) {
    const ratio = contrastRatio(rgbToHex(row.border), rgbToHex(row.background))
    expect(
      ratio,
      `outline border ${row.border} vs ${row.background} = ${ratio.toFixed(2)}:1`,
    ).toBeGreaterThanOrEqual(3)
  }
})
