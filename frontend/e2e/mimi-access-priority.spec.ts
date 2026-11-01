import { expect, type Page } from '@playwright/test'
import { test } from './fixtures/tasks'

const conversation = {
  id: 'synthetic-access-conversation', title: 'Mimi · truy cập nhanh tổng hợp', sensitivity: 'standard', generation: 1,
  messages: [], runs: [], change_sets: [], receipts: [], events: [], feedback: [],
}

async function setup(page: Page, available = true, delaySnapshot = false) {
  const context = page.context()
  // Fixture fallthrough cannot reach any backend or external/provider service.
  await context.route('**/*', route => {
    const url = new URL(route.request().url())
    if (url.origin !== 'http://127.0.0.1:15211') return route.abort('blockedbyclient')
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/auth/')) {
      return route.fulfill({ status: 404, json: { detail: 'synthetic_unsupplied_endpoint' } })
    }
    return route.continue()
  })
  await page.route('**/api/me', route => route.fulfill({ json: { email: 'synthetic@example.test',
    expires_at: '2099-01-01T00:00:00Z', private_until: null, private_locked_until: null,
    pin_is_set: true, pin_is_bootstrap: false, mimi_available: available } }))
  const mutations: string[] = []
  await page.route('**/api/mimi/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    // Existing base lifecycle probe; never a real provider call in this lane.
    if (path.endsWith('/metadata-warmup')) return route.fulfill({ json: { status: 'not_applicable', paid_calls: 0 } })
    if (request.method() !== 'GET') mutations.push(`${request.method()} ${path}`)
    if (path.endsWith('/current') || path.endsWith(`/conversations/${conversation.id}`)) {
      if (delaySnapshot) await new Promise(resolve => setTimeout(resolve, 200))
      return route.fulfill({ json: conversation })
    }
    if (path.endsWith('/conversations')) return route.fulfill({ json: { items: [{
      ...conversation, metadata_version: 1, archived_at: null, updated_at: '2026-11-01T00:00:00Z',
    }], next_cursor: null } })
    if (path.endsWith('/capabilities')) return route.fulfill({ json: {
      context_v1_enabled: false, live_provider_enabled: false, context_limit: 131072,
      output_reserve: 4096, model_selection_enabled: false,
    } })
    return route.fulfill({ status: 404, json: { detail: 'synthetic_unsupplied_mimi_endpoint' } })
  })
  return mutations
}

async function expectDockOnscreen(page: Page) {
  const dock = page.getByTestId('mimi-side-chat')
  await expect(dock).toBeVisible()
  await expect(page.getByTestId('mimi-input')).toBeFocused()
  const box = (await dock.boundingBox())!
  expect(box.y).toBeGreaterThanOrEqual(0)
  expect(box.y + box.height).toBeLessThanOrEqual(page.viewportSize()!.height + 1)
  await expect(page.getByTestId('mimi-input')).toBeInViewport()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await expect(page.getByTestId('mimi-quick-access')).toBeHidden()
}

test('access: scroll keeps menu and icon-only FAB reachable, draft and focus survive dock opening', async ({ page }, info) => {
  const mutations = await setup(page, true, true)
  await page.goto('/')
  const draft = page.getByTestId('quick-add-input')
  await draft.fill('Bản nháp Task giữ nguyên · tiếng Việt 🚲')
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(100)
  const menu = page.getByTestId('app-menu-open')
  await expect(menu).toBeInViewport()
  const trigger = page.getByTestId('mimi-quick-access')
  await expect(trigger).toHaveAccessibleName('Chat với Mimi')
  const box = (await trigger.boundingBox())!
  expect(box.width).toBeGreaterThanOrEqual(44)
  expect(box.height).toBeGreaterThanOrEqual(44)
  expect((await trigger.innerText()).trim()).toBe('')
  if (page.viewportSize()!.width < 1024) {
    const nav = (await page.getByRole('tablist', { name: 'Chọn nội dung' }).boundingBox())!
    expect(box.y + box.height).toBeLessThanOrEqual(nav.y)
  }
  await trigger.focus()
  await expect(page.getByRole('tooltip')).toContainText('Chat với Mimi · Alt+A')
  await page.screenshot({ path: info.outputPath('scrolled-access.png'), scale: 'css' })
  await page.keyboard.press('Enter')
  await expectDockOnscreen(page)
  await expect(page.getByTestId('leave-draft-confirm')).toBeHidden()
  await page.screenshot({ path: info.outputPath('dock-from-scroll.png'), scale: 'css' })
  await page.getByRole('button', { name: 'Đóng side-chat', exact: true }).click()
  await expect(trigger).toBeFocused()
  await expect(draft).toHaveValue('Bản nháp Task giữ nguyên · tiếng Việt 🚲')
  await expect(page.getByRole('tablist', { name: 'Chọn nội dung' }).getByRole('tab')).toHaveCount(5)
  expect(mutations).toEqual([])
})

test('access: menu opens dock after scroll and returns focus to the application menu', async ({ page }) => {
  const mutations = await setup(page)
  await page.goto('/')
  await page.getByTestId('quick-add-input').fill('Nháp giữ qua menu')
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
  await page.getByTestId('app-menu-open').click()
  await page.getByTestId('mimi-dock-open').click()
  await expect(page.getByTestId('app-menu')).toBeHidden()
  await expectDockOnscreen(page)
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('mimi-side-chat')).toBeHidden()
  await expect(page.getByTestId('app-menu-open')).toBeFocused()
  await expect(page.getByTestId('quick-add-input')).toHaveValue('Nháp giữ qua menu')
  expect(mutations).toEqual([])
})

test('access: shortcut ignores input, IME, repeat, browser modifiers and claimed keys', async ({ page }) => {
  const mutations = await setup(page)
  await page.goto('/')
  await page.getByTestId('quick-add-input').focus()
  await page.keyboard.press('Alt+a')
  await expect(page.getByTestId('mimi-side-chat')).toBeHidden()
  await page.evaluate(() => {
    const editable = document.createElement('div')
    editable.contentEditable = 'true'
    editable.dataset.testid = 'synthetic-contenteditable'
    document.body.append(editable)
    editable.focus()
  })
  await page.keyboard.press('Alt+a')
  await expect(page.getByTestId('mimi-side-chat')).toBeHidden()
  await page.getByTestId('app-menu-open').focus()
  for (const override of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true },
    { repeat: true }, { isComposing: true }, { keyCode: 229 }, { code: 'KeyB' }]) {
    await page.evaluate(override => window.dispatchEvent(new KeyboardEvent('keydown', {
      altKey: true, code: 'KeyA', bubbles: true, cancelable: true, ...override,
    })), override)
    await expect(page.getByTestId('mimi-side-chat')).toBeHidden()
  }
  await page.evaluate(() => {
    const event = new KeyboardEvent('keydown', { altKey: true, code: 'KeyA', cancelable: true })
    event.preventDefault()
    window.dispatchEvent(event)
  })
  await expect(page.getByTestId('mimi-side-chat')).toBeHidden()
  await page.keyboard.press('Alt+a')
  await expectDockOnscreen(page)
  if (page.viewportSize()!.width >= 1280) {
    await page.getByTestId('app-menu-open').focus()
    await page.keyboard.press('Alt+a')
    await expect(page.getByTestId('mimi-input')).toBeFocused()
    await expect(page.getByTestId('mimi-side-chat')).toHaveCount(1)
  }
  // Editing inside the already-open dock must not replace its draft or layer.
  await page.getByTestId('mimi-input').fill('Nháp Mimi đang nhập')
  await page.keyboard.press('Alt+a')
  await expect(page.getByTestId('mimi-input')).toHaveValue('Nháp Mimi đang nhập')
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('app-menu-open')).toBeFocused()
  expect(mutations).toEqual([])
})

test('access: modal and nested menu own keyboard input, Escape dismisses only the top layer', async ({ page }, info) => {
  const mutations = await setup(page)
  await page.goto('/')
  await page.getByTestId('app-menu-open').click()
  await page.keyboard.press('Alt+a')
  await expect(page.getByTestId('app-menu')).toBeVisible()
  await expect(page.getByTestId('mimi-side-chat')).toBeHidden()
  await page.getByTestId('private-pin-change-open').click()
  await expect(page.getByRole('dialog', { name: 'Đổi PIN', exact: true })).toBeVisible()
  await page.keyboard.press('Alt+a')
  await expect(page.getByTestId('mimi-side-chat')).toBeHidden()
  await page.keyboard.press('Escape')
  await page.getByTestId('mimi-quick-access').click()
  await expectDockOnscreen(page)
  await page.getByRole('button', { name: 'Tùy chọn side-chat', exact: true }).click()
  await page.keyboard.press('Alt+a')
  await expect(page.getByRole('menu')).toBeVisible()
  await page.getByRole('menuitem', { name: 'Lịch sử hội thoại', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Lịch sử hội thoại', exact: true })).toBeVisible()
  await page.keyboard.press('Alt+a')
  await page.screenshot({ path: info.outputPath('nested-history.png'), scale: 'css' })
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog', { name: 'Lịch sử hội thoại', exact: true })).toBeHidden()
  await expect(page.getByTestId('mimi-side-chat')).toBeVisible()
  await page.getByRole('button', { name: 'Đóng side-chat', exact: true }).click()
  expect(mutations).toEqual([])
})

test('access: workspace shortcut and menu focus the existing composer without a second dock', async ({ page }) => {
  const mutations = await setup(page)
  await page.goto('/')
  await page.getByRole('tab', { name: 'Mimi', exact: true }).click()
  await page.getByTestId('mimi-input').fill('Giữ nháp workspace 🚲')
  await page.getByTestId('app-menu-open').focus()
  await page.keyboard.press('Alt+a')
  await expect(page.getByTestId('mimi-input')).toBeFocused()
  await expect(page.getByTestId('mimi-side-chat')).toBeHidden()
  await page.getByTestId('app-menu-open').click()
  await page.getByTestId('mimi-dock-open').click()
  await expect(page.getByTestId('mimi-input')).toBeFocused()
  await expect(page.getByTestId('mimi-input')).toHaveValue('Giữ nháp workspace 🚲')
  await expect(page.getByTestId('mimi-side-chat')).toBeHidden()
  await expect(page.getByTestId('mimi-quick-access')).toBeHidden()
  expect(mutations).toEqual([])
})

test('access: responsive shell clears bottom navigation and keeps dock/composer onscreen', async ({ page }, info) => {
  const mutations = await setup(page)
  await page.goto('/')
  for (const viewport of [{ width: 360, height: 740 }, { width: 1024, height: 768 }, { width: 1440, height: 900 }]) {
    await page.setViewportSize(viewport)
    if (info.project.use.hasTouch) await page.getByTestId('mimi-quick-access').tap()
    else await page.getByTestId('mimi-quick-access').click()
    // Move the mouse away from the unchanged context meter's hover surface.
    await page.mouse.move(0, 0)
    await expectDockOnscreen(page)
    await expect(page.getByRole('button', { name: 'Đóng thống kê hội thoại', exact: true })).toBeHidden()
    await page.screenshot({ path: info.outputPath(`shell-${viewport.width}.png`), scale: 'css' })
    await page.getByRole('button', { name: 'Đóng side-chat', exact: true }).click()
    await expect(page.getByTestId('mimi-quick-access')).toBeFocused()
  }
  expect(mutations).toEqual([])
})

test('access: unavailable Mimi preserves the existing gate and keyboard does not open it', async ({ page }) => {
  await setup(page, false)
  await page.goto('/')
  await expect(page.getByTestId('mimi-quick-access')).toBeHidden()
  await expect(page.getByRole('tab', { name: 'Mimi', exact: true })).toBeDisabled()
  await page.getByTestId('app-menu-open').focus()
  await page.keyboard.press('Alt+a')
  await expect(page.getByTestId('mimi-side-chat')).toBeHidden()
})
