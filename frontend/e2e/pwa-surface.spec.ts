import type { Page } from '@playwright/test'

import { expect, test } from './fixtures/tasks'

type SurfaceStyles = {
  background: string
  border: string
}

async function readSurfaceStyles(page: Page): Promise<Record<string, SurfaceStyles>> {
  return page.evaluate(() => {
    const selectors = {
      unlock: '[data-testid="private-unlock-open"]',
      quickAdd: '[data-testid="quick-add-input"]',
      reschedule: '[data-testid="task-reschedule-today"]',
      checkbox: '[data-testid="task-checkbox"]',
    } as const
    return Object.fromEntries(
      Object.entries(selectors).map(([name, selector]) => {
        const element = document.querySelector<HTMLElement>(selector)
        if (!element) throw new Error(`Missing ${selector}`)
        const style = getComputedStyle(element)
        return [name, { background: style.backgroundColor, border: style.borderTopColor }]
      }),
    ) as Record<string, SurfaceStyles>
  })
}

test.describe('024 iOS PWA surfaces', () => {
  test.describe('mobile', () => {
    test.skip(({ isMobile }) => !isMobile, 'mobile project only')
    test('light-only controls do not change under dark OS scheme', async ({ page, taskApi }) => {
      taskApi.privateUntil = null
      await page.goto('/')

      await expect(page.getByTestId('private-unlock-open')).toHaveAttribute(
        'data-variant',
        'softRose',
      )
      await expect(page.getByTestId('task-reschedule-today').first()).toHaveAttribute(
        'data-variant',
        'softRose',
      )
      await expect(page.getByTestId('filter-open')).toHaveAttribute('data-variant', 'selected')

      await page.emulateMedia({ colorScheme: 'light' })
      const light = await readSurfaceStyles(page)
      await page.emulateMedia({ colorScheme: 'dark' })
      const dark = await readSurfaceStyles(page)

      expect(dark, 'light-only control surfaces must be OS-scheme invariant').toEqual(light)
      expect(light.unlock.background).not.toBe('rgba(0, 0, 0, 0)')
      expect(light.reschedule.background).not.toBe('rgba(0, 0, 0, 0)')
      expect(light.quickAdd.background).not.toBe('rgb(75, 75, 75)')

      const overflow = await page.evaluate(() => {
        const scrolling = document.scrollingElement ?? document.documentElement
        return {
          scrollWidth: scrolling.scrollWidth,
          clientWidth: scrolling.clientWidth,
        }
      })
      expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth)
    })

    test('outer canvas covers the mobile viewport without horizontal overscroll', async ({ page }) => {
      await page.goto('/')
      const canvas = await page.evaluate(() => {
        const selectors = ['html', 'body', '#root', 'main']
        const viewportHeight = window.innerHeight
        const viewportWidth = window.innerWidth
        return {
          viewportHeight,
          viewportWidth,
          scrollWidth: (document.scrollingElement ?? document.documentElement).scrollWidth,
          elements: selectors.map((selector) => {
            const element = document.querySelector<HTMLElement>(selector)
            if (!element) throw new Error(`Missing ${selector}`)
            const style = getComputedStyle(element)
            const rect = element.getBoundingClientRect()
            return {
              selector,
              background: style.backgroundColor,
              minHeight: parseFloat(style.minHeight),
              height: rect.height,
            }
          }),
        }
      })

      const expectedCanvas = 'rgb(243, 238, 239)'
      expect(canvas.scrollWidth).toBeLessThanOrEqual(canvas.viewportWidth)
      for (const element of canvas.elements) {
        expect(element.background, `${element.selector} canvas`).toBe(expectedCanvas)
        expect(element.minHeight, `${element.selector} min-height`).toBeGreaterThanOrEqual(
          canvas.viewportHeight,
        )
        expect(element.height, `${element.selector} viewport coverage`).toBeGreaterThanOrEqual(
          canvas.viewportHeight,
        )
      }
    })
  })

  test.describe('desktop', () => {
    test.skip(({ isMobile }) => isMobile, 'desktop project only')
    test('keeps a changed, visible, contrast-safe focus indicator', async ({ page }) => {
      await page.goto('/')
      const input = page.getByTestId('quick-add-input')
      const before = await input.evaluate((element) => {
        const style = getComputedStyle(element)
        return {
          border: style.borderTopColor,
          boxShadow: style.boxShadow,
          outline: style.outline,
        }
      })
      await input.focus()
      await page.waitForTimeout(250)
      const focus = await input.evaluate((element) => {
        const canvas = document.createElement('canvas')
        canvas.width = 1
        canvas.height = 1
        const context = canvas.getContext('2d')
        if (!context) throw new Error('Unable to create contrast canvas')
        const rendered = (color: string) => {
          context.clearRect(0, 0, 1, 1)
          context.fillStyle = color
          context.fillRect(0, 0, 1, 1)
          const [red, green, blue, alpha] = context.getImageData(0, 0, 1, 1).data
          return { red, green, blue, alpha: alpha / 255 }
        }
        const style = getComputedStyle(element)
        return {
          border: style.borderTopColor,
          boxShadow: style.boxShadow,
          outline: style.outline,
          borderColor: rendered(style.borderTopColor),
          backgroundColor: rendered(style.backgroundColor),
        }
      })
      const changed =
        before.border !== focus.border ||
        before.boxShadow !== focus.boxShadow ||
        before.outline !== focus.outline
      expect(changed, 'focus must change a rendered indicator property').toBe(true)
      expect(
        focus.boxShadow !== 'none' ||
          focus.border !== before.border ||
          focus.outline !== before.outline,
        'focus indicator must remain visible after focus settles',
      ).toBe(true)

      const relativeLuminance = (red: number, green: number, blue: number) => {
        const linear = [red, green, blue].map((channel) => {
          const value = channel / 255
          return value <= 0.03928
            ? value / 12.92
            : Math.pow((value + 0.055) / 1.055, 2.4)
        })
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
      }
      const borderLuminance = relativeLuminance(
        focus.borderColor.red,
        focus.borderColor.green,
        focus.borderColor.blue,
      )
      const backgroundLuminance = relativeLuminance(
        focus.backgroundColor.red,
        focus.backgroundColor.green,
        focus.backgroundColor.blue,
      )
      const lighter = Math.max(borderLuminance, backgroundLuminance)
      const darker = Math.min(borderLuminance, backgroundLuminance)
      expect((lighter + 0.05) / (darker + 0.05)).toBeGreaterThanOrEqual(3)
    })
  })
})
