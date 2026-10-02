import { expect, test as base } from './fixtures/tasks'
import type { Note } from '../src/note-ui'

const noteId = '2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f4301'
const noteItemIds = ['2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5200', '2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5201', '2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5202', '2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5203', '2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5204', '2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5205', '2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5206', '2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5207', '2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5208'] as const
const longText = 'Kiểm tra tiếng Việt và nội dung nhiều dòng. '.repeat(6) + 'ChuỗiKhôngKhoảngTrắng'.repeat(12)
const test = base.extend<{ notes: {
  note: Note
  patches: object[]
  patchAttempts: Array<{ path: string; body: object; status: number }>
  failuresRemaining: number
  failedResponses: number
  confirmedResponses: number
  firstAttemptHold: Promise<void> | null
  secondAttemptHold: Promise<void> | null
} }>({
  notes: [async ({ page }, use) => {
    const state = {
      note: {
        id: noteId, title: 'Checklist tổng hợp', body_md: 'Dữ liệu hoàn toàn giả lập.',
        pinned: false, is_private: false, created_at: '2026-09-07T00:00:00Z', updated_at: null,
        items: Array.from({ length: 9 }, (_, index) => ({
          id: noteItemIds[index], content: index === 5 ? longText : `Mục ${index}`,
          is_completed: index % 2 === 0, position: index,
        })),
      } satisfies Note,
      patches: [] as object[],
      patchAttempts: [] as Array<{ path: string; body: object; status: number }>,
      failuresRemaining: 0,
      failedResponses: 0,
      confirmedResponses: 0,
      firstAttemptHold: null as Promise<void> | null,
      secondAttemptHold: null as Promise<void> | null,
    }
    await page.route('**/api/notes**', async (route) => {
      const request = route.request()
      const url = new URL(request.url())
      if (request.method() === 'GET') {
        state.note.items.sort((left, right) => left.position - right.position)
        await route.fulfill({ json: { items: Number(url.searchParams.get('offset')) ? [] : [state.note] } })
        return
      }
      if (request.method() === 'PATCH' && url.pathname === `/api/notes/${noteId}/items/positions`) {
        const payload = request.postDataJSON() as { items: Array<{ id: string; position: number }> }
        state.patches.push(payload)
        const positions = new Map(payload.items.map((entry) => [entry.id, entry.position]))
        state.note.items = state.note.items.map((entry) => ({
          ...entry,
          position: positions.get(entry.id) ?? entry.position,
        })).sort((left, right) => left.position - right.position)
        await route.fulfill({ json: payload.items.flatMap(({ id }) => {
          const item = state.note.items.find((entry) => entry.id === id)
          return item ? [item] : []
        }) })
        return
      }
      const item = state.note.items.find((entry) => url.pathname.endsWith(`/items/${entry.id}`))
      if (request.method() === 'PATCH' && item) {
        const changes = request.postDataJSON() as object
        state.patches.push(changes)
        const attempt = { path: url.pathname, body: changes, status: 0 }
        state.patchAttempts.push(attempt)
        const attemptHold = state.patchAttempts.length === 1
          ? state.firstAttemptHold
          : state.patchAttempts.length === 2 ? state.secondAttemptHold : null
        if (attemptHold) await attemptHold
        if (state.failuresRemaining > 0) {
          state.failuresRemaining -= 1
          await route.fulfill({ status: 500, json: { detail: 'Không lưu được mục thử nghiệm' } })
          attempt.status = 500
          state.failedResponses += 1
          return
        }
        Object.assign(item, changes)
        await route.fulfill({ json: item })
        attempt.status = 200
        state.confirmedResponses += 1
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
  const row = card.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5201"]')
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
  await expect(card.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5200"]')).toBeHidden()
  await expect(card.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5207"]')).toBeHidden()
  await card.getByTestId('note-items-remaining-toggle').click()
  await expect(card.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5207"]')).toBeVisible()
  await card.getByTestId('note-items-remaining-toggle').click()
  await expect(card.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5207"]')).toBeHidden()
  await completed.click()
  const done = card.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5200"]')
  await expect(done).toBeVisible()
  await done.getByTestId('note-item-content').click()
  await expect(card.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5200"]').getByRole('checkbox')).not.toBeChecked()
  const open = card.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5201"]').getByRole('checkbox')
  await open.focus()
  await open.press('Space')
  await expect(card.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5201"]').getByRole('checkbox')).toBeChecked()
  await expect(card.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5201"]').getByRole('checkbox')).toBeFocused()
  await completed.click()
  await expect(card.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5201"]')).toBeHidden()
  await expect(page.getByTestId('note-detail-dialog')).toHaveCount(0)
  expect(notes.patches).toEqual([{ is_completed: false }, { is_completed: true }])
  expect(notes.note.items.map((item) => item.position)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8])
})

test('collapsed completed group receives keyboard focus after checking an open item', async ({ page }) => {
  const card = page.getByTestId('note-card')
  const checkbox = card.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5201"]').getByRole('checkbox')
  await checkbox.focus()
  await checkbox.press('Space')
  await expect(card.getByTestId('note-items-completed-toggle')).toHaveText('Đã xong (6)')
  await expect(card.getByTestId('note-items-completed-toggle')).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(card.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5201"]').getByRole('checkbox')).toBeVisible()
})

test('detail text toggles, whitespace does not, long text fits and editing persists', async ({ page, notes }, testInfo) => {
  await page.getByTestId('note-title').click()
  const dialog = page.getByTestId('note-detail-dialog')
  const row = dialog.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5201"]')
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
  await dialog.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5201"]').getByRole('checkbox').click()
  await expect(dialog.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5201"]').getByRole('checkbox')).not.toBeChecked()
  const longRow = dialog.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5205"]')
  await expect(longRow.getByTestId('note-item-content')).toHaveText(longText)
  expect(await longRow.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  await row.getByTestId('note-item-edit').click()
  await row.getByTestId('note-item-edit-input').fill('Nội dung đã sửa')
  await row.getByTestId('note-item-edit-save').click()
  await expect(row.getByTestId('note-item-content')).toHaveText('Nội dung đã sửa')
  await expect.poll(() => notes.patches).toEqual([{ is_completed: true }, { is_completed: false }, { content: 'Nội dung đã sửa' }])
  await dialog.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5203"]').getByTestId('note-item-up').click()
  await expect(dialog.getByTestId('note-item').first()).toHaveAttribute('data-note-item-id', '2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5203')
  await expect.poll(() => notes.patches[3]).toEqual({ items: [
    { id: '2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5203', position: 1 },
    { id: '2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5201', position: 3 },
  ] })
  await dialog.evaluate((element) => { element.scrollTop = 0 })
  if (process.env.CAPTURE_TASK045 === '1') await page.screenshot({ path: testInfo.outputPath('notes-detail.png') })
})

test('5xx retains optimistic checklist state and replays the same queued patch until confirmed', async ({ page, notes }) => {
  let releaseFirst: () => void = () => undefined
  let releaseSecond: () => void = () => undefined
  notes.firstAttemptHold = new Promise<void>((resolve) => { releaseFirst = resolve })
  notes.secondAttemptHold = new Promise<void>((resolve) => { releaseSecond = resolve })
  notes.failuresRemaining = 1
  const card = page.getByTestId('note-card')
  const row = card.locator('[data-note-item-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5201"]')
  const checkbox = row.getByRole('checkbox')
  const completedGroup = card.getByTestId('note-items-completed-toggle')
  await completedGroup.click()
  await expect(completedGroup).toHaveAttribute('aria-expanded', 'true')
  await checkbox.focus()
  await checkbox.press('Space')
  await expect.poll(() => notes.patchAttempts.length).toBe(1)
  await expect(page.getByTestId('outbox-indicator').first()).toBeVisible()
  await expect(checkbox).toBeChecked()
  await expect(checkbox).toBeFocused()
  expect(notes.patchAttempts).toEqual([{
    path: `/api/notes/${noteId}/items/${noteItemIds[1]}`,
    body: { is_completed: true },
    status: 0,
  }])

  const readOutbox = () => page.evaluate(() => new Promise<Array<Record<string, unknown>>>((resolve, reject) => {
    const open = indexedDB.open('microsched-outbox')
    open.onerror = () => reject(open.error)
    open.onsuccess = () => {
      const db = open.result
      const request = db.transaction('outbox', 'readonly').objectStore('outbox').getAll()
      request.onerror = () => { db.close(); reject(request.error) }
      request.onsuccess = () => { db.close(); resolve(request.result) }
    }
  }))
  const heldRows = await readOutbox()
  expect(heldRows).toHaveLength(1)
  expect(heldRows[0]).toMatchObject({
    operation_kind: 'note_item.update',
    path: `/api/notes/${noteId}/items/${noteItemIds[1]}`,
    entity_id: noteItemIds[1],
    parent_id: noteId,
    body: { is_completed: true },
    payload_json: '{"is_completed":true}',
    state: 'outcome_unknown',
    attempts: 1,
  })
  const digest = heldRows[0].payload_sha256
  expect(digest).toMatch(/^[a-f0-9]{64}$/)

  releaseFirst()
  await expect.poll(() => notes.failedResponses).toBe(1)
  await expect.poll(async () => (await readOutbox())[0]).toMatchObject({
    operation_kind: 'note_item.update',
    entity_id: noteItemIds[1],
    body: { is_completed: true },
    payload_json: '{"is_completed":true}',
    payload_sha256: digest,
    state: 'outcome_unknown',
    attempts: 1,
    last_error_code: 'HTTP_500',
  })
  await expect(checkbox).toBeChecked()
  await expect(checkbox).toBeFocused()
  await expect(page.getByTestId('outbox-indicator').first()).toContainText('1 đang chờ gửi')

  await expect.poll(() => notes.patchAttempts.length, { timeout: 10000 }).toBe(2)
  expect(notes.patchAttempts[1]).toEqual({
    path: `/api/notes/${noteId}/items/${noteItemIds[1]}`,
    body: { is_completed: true },
    status: 0,
  })
  const retryRows = await readOutbox()
  expect(retryRows).toHaveLength(1)
  expect(retryRows[0]).toMatchObject({ payload_sha256: digest, state: 'outcome_unknown', attempts: 2 })

  releaseSecond()
  await expect.poll(() => notes.confirmedResponses).toBe(1)
  await expect.poll(readOutbox).toHaveLength(0)
  expect(notes.patchAttempts.map((attempt) => attempt.status)).toEqual([500, 200])
  expect(notes.patchAttempts[1]).toEqual({
    path: notes.patchAttempts[0].path,
    body: notes.patchAttempts[0].body,
    status: 200,
  })
  expect(notes.note.items.find((item) => item.id === noteItemIds[1])?.is_completed).toBe(true)
  await expect(checkbox).toBeChecked()
  await expect(checkbox).toBeFocused()
})
