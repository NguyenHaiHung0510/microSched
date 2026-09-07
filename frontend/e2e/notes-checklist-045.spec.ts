import { expect, test as base } from './fixtures/tasks'
import type { Note } from '../src/note-ui'

const noteId = 'note-checklist-045'
const longText = 'Kiểm tra tiếng Việt và nội dung nhiều dòng. '.repeat(6) + 'ChuỗiKhôngKhoảngTrắng'.repeat(12)
const test = base.extend<{ notes: { note: Note; patches: object[]; fail: boolean; hold: Promise<void> | null } }>({
  notes: [async ({ page }, use) => {
    const state = {
      note: {
        id: noteId, title: 'Checklist tổng hợp', body_md: 'Dữ liệu hoàn toàn giả lập.',
        pinned: false, is_private: false, created_at: '2026-09-07T00:00:00Z', updated_at: null,
        items: Array.from({ length: 9 }, (_, index) => ({
          id: `item-${index}`, content: index === 5 ? longText : `Mục ${index}`,
          is_completed: index % 2 === 0, position: index,
        })),
      } satisfies Note,
      patches: [] as object[], fail: false, hold: null as Promise<void> | null,
    }
    await page.route('**/api/notes**', async (route) => {
      const request = route.request()
      const url = new URL(request.url())
      if (request.method() === 'GET') {
        state.note.items.sort((left, right) => left.position - right.position)
        await route.fulfill({ json: { items: Number(url.searchParams.get('offset')) ? [] : [state.note] } })
        return
      }
      const item = state.note.items.find((entry) => url.pathname.endsWith(`/items/${entry.id}`))
      if (request.method() === 'PATCH' && item) {
        const changes = request.postDataJSON() as object
        state.patches.push(changes)
        if (state.hold) await state.hold
        if (state.fail) {
          await route.fulfill({ status: 500, json: { detail: 'Không lưu được mục thử nghiệm' } })
          return
        }
        Object.assign(item, changes)
        await route.fulfill({ json: item })
        return
      }
      await route.fulfill({ status: 404, json: { detail: 'Synthetic fixture boundary' } })
    })
    await use(state)
  }, { auto: true }],
})

test.beforeEach(async ({ page }) => {
  await page.goto('/')
  await page.getByRole('tab', { name: 'Ghi chú' }).click()
  await expect(page.getByTestId('note-card')).toBeVisible()
})

test('row whitespace opens detail without toggling; explicit title still opens detail', async ({ page, notes }) => {
  const card = page.getByTestId('note-card')
  const row = card.locator('[data-note-item-id="item-1"]')
  const box = await row.boundingBox()
  if (!box) throw new Error('Checklist row missing')
  await row.click({ position: { x: box.width - 4, y: box.height / 2 } })
  await expect(page.getByTestId('note-detail-dialog')).toBeVisible()
  expect(notes.patches).toEqual([])
  await page.keyboard.press('Escape')
  await card.getByTestId('note-title').click()
  await expect(page.getByTestId('note-detail-dialog')).toBeVisible()
  expect(notes.patches).toEqual([])
})

test('groups disclose reversibly and checkbox/text update state without position writes', async ({ page, notes }, testInfo) => {
  const card = page.getByTestId('note-card')
  const completed = card.getByTestId('note-items-completed-toggle')
  await expect(completed).toHaveText('Đã xong (5)')
  await expect(completed).toHaveAttribute('aria-expanded', 'false')
  if (process.env.CAPTURE_TASK045 === '1') await page.screenshot({ path: testInfo.outputPath('notes-card.png') })
  await expect(card.locator('[data-note-item-id="item-0"]')).toBeHidden()
  await expect(card.locator('[data-note-item-id="item-7"]')).toBeHidden()
  await card.getByTestId('note-items-remaining-toggle').click()
  await expect(card.locator('[data-note-item-id="item-7"]')).toBeVisible()
  await card.getByTestId('note-items-remaining-toggle').click()
  await expect(card.locator('[data-note-item-id="item-7"]')).toBeHidden()
  await completed.click()
  const done = card.locator('[data-note-item-id="item-0"]')
  await expect(done).toBeVisible()
  await done.getByTestId('note-item-content').click()
  await expect(card.locator('[data-note-item-id="item-0"]').getByRole('checkbox')).not.toBeChecked()
  const open = card.locator('[data-note-item-id="item-1"]').getByRole('checkbox')
  await open.focus()
  await open.press('Space')
  await expect(card.locator('[data-note-item-id="item-1"]').getByRole('checkbox')).toBeChecked()
  await expect(card.locator('[data-note-item-id="item-1"]').getByRole('checkbox')).toBeFocused()
  await completed.click()
  await expect(card.locator('[data-note-item-id="item-1"]')).toBeHidden()
  await expect(page.getByTestId('note-detail-dialog')).toHaveCount(0)
  expect(notes.patches).toEqual([{ is_completed: false }, { is_completed: true }])
  expect(notes.note.items.map((item) => item.position)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8])
})

test('collapsed completed group receives keyboard focus after checking an open item', async ({ page }) => {
  const card = page.getByTestId('note-card')
  const checkbox = card.locator('[data-note-item-id="item-1"]').getByRole('checkbox')
  await checkbox.focus()
  await checkbox.press('Space')
  await expect(card.getByTestId('note-items-completed-toggle')).toHaveText('Đã xong (6)')
  await expect(card.getByTestId('note-items-completed-toggle')).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(card.locator('[data-note-item-id="item-1"]').getByRole('checkbox')).toBeVisible()
})

test('detail text toggles, whitespace does not, long text fits and editing persists', async ({ page, notes }, testInfo) => {
  await page.getByTestId('note-title').click()
  const dialog = page.getByTestId('note-detail-dialog')
  const row = dialog.locator('[data-note-item-id="item-1"]')
  const toggle = row.getByTestId('note-item-toggle')
  const geometry = await toggle.evaluate((element) => {
    const rect = element.getBoundingClientRect()
    const parent = element.parentElement!.getBoundingClientRect()
    return { width: rect.width, parentWidth: parent.width, height: rect.height }
  })
  expect(geometry.parentWidth - geometry.width).toBeGreaterThan(15)
  expect(geometry.height).toBeGreaterThanOrEqual(44)
  const whitespace = toggle.locator('..')
  const box = await whitespace.boundingBox()
  if (!box) throw new Error('Checklist whitespace missing')
  await whitespace.click({ position: { x: box.width - 2, y: 10 } })
  expect(notes.patches).toEqual([])
  await row.getByTestId('note-item-content').click()
  await expect(dialog.getByTestId('note-items-completed-toggle')).toHaveText('Đã xong (6)')
  await dialog.getByTestId('note-items-completed-toggle').click()
  await dialog.locator('[data-note-item-id="item-1"]').getByRole('checkbox').click()
  await expect(dialog.locator('[data-note-item-id="item-1"]').getByRole('checkbox')).not.toBeChecked()
  const longRow = dialog.locator('[data-note-item-id="item-5"]')
  await expect(longRow.getByTestId('note-item-content')).toHaveText(longText)
  expect(await longRow.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  await row.getByTestId('note-item-edit').click()
  await row.getByTestId('note-item-edit-input').fill('Nội dung đã sửa')
  await row.getByTestId('note-item-edit-save').click()
  await expect(row.getByTestId('note-item-content')).toHaveText('Nội dung đã sửa')
  expect(notes.patches).toEqual([{ is_completed: true }, { is_completed: false }, { content: 'Nội dung đã sửa' }])
  await dialog.locator('[data-note-item-id="item-3"]').getByTestId('note-item-up').click()
  await expect(dialog.getByTestId('note-item').first()).toHaveAttribute('data-note-item-id', 'item-3')
  expect(notes.patches.slice(3)).toEqual(expect.arrayContaining([{ position: 1 }, { position: 3 }]))
  await dialog.evaluate((element) => { element.scrollTop = 0 })
  if (process.env.CAPTURE_TASK045 === '1') await page.screenshot({ path: testInfo.outputPath('notes-detail.png') })
})

test('pending blocks duplicate toggles and failure preserves state and focus', async ({ page, notes }) => {
  let finish: () => void = () => undefined
  notes.hold = new Promise<void>((resolve) => { finish = resolve })
  notes.fail = true
  const card = page.getByTestId('note-card')
  const row = card.locator('[data-note-item-id="item-1"]')
  const checkbox = row.getByRole('checkbox')
  await checkbox.focus()
  await checkbox.press('Space')
  await expect(checkbox).toBeDisabled()
  await row.getByTestId('note-item-content').click({ force: true })
  expect(notes.patches).toHaveLength(1)
  finish()
  await expect(card.getByText('Không lưu được mục thử nghiệm')).toBeVisible()
  await expect(checkbox).toBeEnabled()
  await expect(checkbox).not.toBeChecked()
  await expect(checkbox).toBeFocused()
  expect(notes.patches).toHaveLength(1)
})
