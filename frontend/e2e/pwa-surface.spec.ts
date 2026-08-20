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
  })

  test.describe('desktop', () => {
    test.skip(({ isMobile }) => isMobile, 'desktop project only')
    test('keeps a visible focus boundary for the quick-add input', async ({ page }) => {
      await page.goto('/')
      const input = page.getByTestId('quick-add-input')
      await input.focus()
      const focus = await input.evaluate((element) => {
        const style = getComputedStyle(element)
        return { border: style.borderTopColor, outline: style.outlineColor }
      })
      expect(focus.border).not.toBe('rgba(0, 0, 0, 0)')
      expect(focus.outline).not.toBe('rgba(0, 0, 0, 0)')
    })
  })
})
