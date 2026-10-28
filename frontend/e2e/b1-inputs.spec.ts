import type { Locator, Page } from '@playwright/test'
import { test as base, expect } from './fixtures/tasks'
import type { MimiConversation } from '../src/mimi-api'
import type { Note } from '../src/note-ui'

const stamp = '2026-10-20T07:00:00Z'
type FeedbackBody = { client_id: string; target_type: string; target_id: string; comment: string; expected: string | null }
const test = base.extend<{ b1: {
  note: Note; creates: string[]; patches: string[]; feedback: FeedbackBody[]
  holdNote: Promise<void> | null; holdFeedback: Promise<void> | null
  failNote: boolean; failFeedback: boolean; wrongAck: boolean
  network: Record<string, number>; pageErrors: string[]
} }>({
  b1: [async ({ page }, use) => {
    const state = {
      note: { id: 'synthetic-note-b1', title: 'Ghi chú chuẩn bị duyệt UI Mimi', body_md: 'Dữ liệu tổng hợp để xem bố cục checklist.', pinned: true, is_private: false, created_at: stamp, updated_at: stamp,
        items: [{ id: 'item-1', content: 'Kiểm tra bố cục trên màn hình nhỏ', is_completed: false, position: 0 }, { id: 'item-2', content: 'Ghi nhận điểm cần trao đổi', is_completed: false, position: 1 }] } as Note,
      creates: [] as string[], patches: [] as string[], feedback: [] as FeedbackBody[], holdNote: null as Promise<void> | null, holdFeedback: null as Promise<void> | null,
      failNote: false, failFeedback: false, wrongAck: false,
      network: {} as Record<string, number>, pageErrors: [] as string[],
    }
    page.on('request', request => {
      const url = new URL(request.url())
      if (!url.pathname.startsWith('/api/')) return
      const key = `${request.method()} ${url.pathname}`
      state.network[key] = (state.network[key] ?? 0) + 1
    })
    page.on('pageerror', error => state.pageErrors.push(error.message))
    const conversation = (id: string): MimiConversation => ({ id, title: id === '01990000-0000-7000-8000-000000000101' ? 'Hội thoại tổng hợp' : 'Hội thoại thứ hai', title_source: 'owner', title_locked: true, metadata_version: 1, updated_at: stamp,
      sensitivity: 'standard', generation: 1, runs: [], receipts: [], events: [], change_sets: [], feedback: [],
      messages: [1, 2].map(sequence => ({ id: `${id}-answer-${sequence}`, sequence, role: 'assistant', content: sequence === 1 ? 'Mình đã sắp xếp các bước chuẩn bị thành một danh sách ngắn để bạn tiện xem lại.' : 'Câu trả lời thứ hai để kiểm tra liên kết bản nháp.', run_id: null, client_id: null, created_at: stamp })),
    })
    await page.route('**/api/me', route => route.fulfill({ json: { email: 'owner@synthetic.invalid', signed_in_at: stamp, expires_at: '2026-10-21T07:00:00Z', private_until: null, private_locked_until: null, pin_is_set: true, pin_is_bootstrap: false, mimi_available: true } }))
    await page.route('**/api/notes**', async route => {
      const req = route.request(), url = new URL(req.url())
      if (req.method() === 'GET') return route.fulfill({ json: { items: Number(url.searchParams.get('offset')) ? [] : [state.note] } })
      if (req.method() === 'POST' && url.pathname.endsWith('/items')) {
        const body = req.postDataJSON() as { content: string; position: number }
        state.creates.push(body.content)
        if (state.holdNote) await state.holdNote
        if (state.failNote) return route.fulfill({ status: 503, json: { detail: 'Synthetic note save failure' } })
        const item = { id: `added-${state.creates.length}`, content: body.content, position: body.position, is_completed: false }
        state.note.items.push(item)
        return route.fulfill({ status: 201, json: item })
      }
      const item = state.note.items.find(item => url.pathname.endsWith(`/items/${item.id}`))
      if (req.method() === 'PATCH' && item) {
        const body = req.postDataJSON() as { content: string }
        state.patches.push(body.content)
        if (state.holdNote) await state.holdNote
        if (state.failNote) return route.fulfill({ status: 503, json: { detail: 'Synthetic note save failure' } })
        Object.assign(item, body)
        return route.fulfill({ json: item })
      }
      return route.fulfill({ status: 404, json: { detail: 'Synthetic note boundary' } })
    })
    await page.route('**/api/mimi/**', async route => {
      const req = route.request(), url = new URL(req.url()), p = url.pathname
      if (p === '/api/mimi/conversations') return route.fulfill({ json: { items: ['01990000-0000-7000-8000-000000000101', '01990000-0000-7000-8000-000000000102'].map(id => ({ ...conversation(id), latest_run_state: null })), next_cursor: null } })
      if (p === '/api/mimi/conversations/current') return route.fulfill({ json: conversation('01990000-0000-7000-8000-000000000101') })
      const conv = p.match(/^\/api\/mimi\/conversations\/([0-9a-f-]{36})$/)
      if (conv) return route.fulfill({ json: conversation(conv[1]) })
      if (p.endsWith('/feedback') && req.method() === 'POST') {
        const body = req.postDataJSON() as FeedbackBody
        state.feedback.push(body)
        if (!body.client_id.startsWith('mimi-positive:')) {
          if (state.holdFeedback) await state.holdFeedback
          if (state.failFeedback) return route.fulfill({ status: 503, json: { detail: 'Synthetic unknown result' } })
        }
        return route.fulfill({ json: { id: `feedback-${state.feedback.length}`, client_id: body.client_id, target_type: body.target_type, target_id: state.wrongAck ? 'wrong-target' : body.target_id, state: 'saved', unresolved: false, created_at: stamp } })
      }
      if (p === '/api/mimi/attention') return route.fulfill({ json: [] })
      if (p === '/api/mimi/capabilities') return route.fulfill({ json: { available: true, synthetic: true } })
      if (p === '/api/mimi/operating-policy') return route.fulfill({ json: { policy: { revision: 0, input_codepoints: 50000, prices: {} }, applies_to: 'next_unsent_wire' } })
      if (p.endsWith('/configuration')) return route.fulfill({ json: { requested_model: null, requested_effort: null, effective_model: null, effective_effort: null } })
      return route.fulfill({ json: { items: [], next_cursor: null } })
    })
    await use(state)
  }, { auto: true }],
})

const input = (page: Page) => page.getByTestId('mimi-positive-detail')
const supplement = (page: Page) => page.getByTestId('mimi-positive-supplement')
async function note(page: Page) {
  await page.goto('/')
  await page.getByRole('tab', { name: 'Ghi chú', exact: true }).click()
  await page.getByTestId('note-title').first().click()
}
async function positive(page: Page, index = 0) {
  await page.getByRole('tab', { name: 'Mimi', exact: true }).click()
  await page.locator('button[aria-label^="Hữu ích · câu trả lời"]').nth(index).click()
  await expect(input(page)).toBeVisible()
}
async function shot(page: Page, name: string) {
  if (process.env.B1_EVIDENCE_DIR) await page.screenshot({ path: `${process.env.B1_EVIDENCE_DIR}/${name}.png`, animations: 'disabled' })
}
async function position(locator: Locator) {
  return locator.evaluate((node: HTMLTextAreaElement) => ({ value: node.value, start: node.selectionStart, end: node.selectionEnd }))
}

test.beforeEach(async ({ page }) => { await page.clock.setFixedTime(new Date('2026-10-20T07:00:00Z')) })
test.afterEach(async ({ b1 }, info) => {
  await info.attach('synthetic-writes', { body: JSON.stringify({ creates: b1.creates, patches: b1.patches, feedback: b1.feedback, network: b1.network, pageErrors: b1.pageErrors }), contentType: 'application/json' })
  expect(b1.pageErrors).toEqual([])
})

test('same baseline caret action passes; middle insert/delete/selection and multiline paste keep native selection', async ({ page }, info) => {
  await note(page)
  await page.getByTestId('note-item-edit').first().click()
  const control = page.getByTestId('note-item-edit-input')
  await control.fill('abcd')
  await control.evaluate((node: HTMLTextAreaElement) => node.setSelectionRange(2, 2))
  await control.press('X')
  const noteCaret = await position(control)
  expect(noteCaret).toEqual({ value: 'abXcd', start: 3, end: 3 })
  await shot(page, `note-${info.project.name}`)
  await page.keyboard.press('Escape')
  await positive(page)
  const el = input(page)
  await el.fill('abcd')
  const handle = await el.elementHandle()
  await el.evaluate((node: HTMLTextAreaElement) => node.setSelectionRange(2, 2))
  await el.press('X')
  expect(await position(el)).toEqual({ value: 'abXcd', start: 3, end: 3 })
  await info.attach('baseline-action-after-fix', { body: JSON.stringify({ action: 'abcd, selection2, pressX', note: noteCaret, positive: await position(el) }), contentType: 'application/json' })
  await el.press('Backspace')
  expect(await position(el)).toEqual({ value: 'abcd', start: 2, end: 2 })
  await el.press('Delete')
  expect(await position(el)).toEqual({ value: 'abd', start: 2, end: 2 })
  await el.evaluate((node: HTMLTextAreaElement) => node.setSelectionRange(1, 3))
  await el.press('X')
  expect(await position(el)).toEqual({ value: 'aX', start: 2, end: 2 })
  await el.evaluate((node: HTMLTextAreaElement) => node.setSelectionRange(1, 1))
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin: new URL(page.url()).origin })
  await page.evaluate(() => navigator.clipboard.writeText('tiếng Việt\n🌸'))
  await el.press('Control+V')
  expect(await position(el)).toEqual({ value: 'atiếng Việt\n🌸X', start: 14, end: 14 })
  expect(await el.evaluate((node, original) => node === original, handle)).toBe(true)
  await shot(page, `feedback-${info.project.name}`)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await info.attach('caret-pass', { body: JSON.stringify(await position(el)), contentType: 'application/json' })
})

test('exact8000 Unicode boundary, all reasons and separate explicit vote/supplement payload', async ({ page, b1 }) => {
  await page.goto('/')
  await positive(page)
  await expect.poll(() => b1.feedback.length).toBe(1)
  expect(b1.feedback[0].comment).toBe('Phản hồi tích cực: Hữu ích.')
  const text = '🌸'.repeat(7999) + 'ệ'
  await input(page).fill(text + 'x')
  await expect(page.getByTestId('mimi-positive-count')).toHaveText('8.001/8.000')
  await expect(page.getByTestId('mimi-positive-submit')).toBeDisabled()
  await input(page).fill(text)
  await expect(page.getByTestId('mimi-positive-count')).toHaveText('8.000/8.000')
  await page.getByTestId('mimi-positive-expected').fill('ữ'.repeat(8000))
  await expect.poll(()=>page.getByTestId('mimi-feedback').evaluate(el=>el.scrollWidth-el.clientWidth)).toBeLessThanOrEqual(1)
  for (const reason of ['Rõ ràng', 'Đúng ý', 'Hữu ích', 'Nhanh', 'Dễ hiểu', 'Khác']) await supplement(page).getByRole('button', { name: reason, exact: true }).click()
  await page.getByTestId('mimi-positive-submit').click()
  await expect.poll(() => b1.feedback.length).toBe(2)
  const sent = b1.feedback[1]
  expect(sent.expected).toBe('ữ'.repeat(8000))
  expect(sent.comment).toContain(text)
  expect(Array.from(sent.comment).length).toBeLessThanOrEqual(10000)
  expect(sent.client_id).not.toBe(b1.feedback[0].client_id)
  expect(sent.target_id).toBe('01990000-0000-7000-8000-000000000101-answer-1')
  await expect(input(page)).toHaveValue('')
})

test('checklist Enter newline, CtrlEnter add/edit; blank, composition and pending do not duplicate writes', async ({ page, b1 }) => {
  await note(page)
  const add = page.getByTestId('note-item-add-input')
  await add.fill(' ')
  await add.press('Control+Enter')
  expect(b1.creates).toHaveLength(0)
  await add.fill('Dòng một')
  await add.press('Enter')
  await add.press('X')
  await expect(add).toHaveValue('Dòng một\nX')
  expect(b1.creates).toHaveLength(0)
  let release!: () => void
  b1.holdNote = new Promise(resolve => { release = resolve })
  await add.press('Control+Enter')
  await expect.poll(() => b1.creates.length).toBe(1)
  await add.press('Control+Enter')
  await add.fill('Bản nháp mới')
  release()
  await expect(page.getByTestId('note-item-add-submit')).toBeEnabled()
  await expect(add).toHaveValue('Bản nháp mới')
  expect(b1.creates).toHaveLength(1)
  b1.holdNote = null
  await page.getByTestId('note-item-edit').first().click()
  const edit = page.getByTestId('note-item-edit-input')
  await edit.fill('Sửa')
  await edit.press('Enter')
  await edit.press('X')
  await expect(edit).toHaveValue('Sửa\nX')
  await edit.press('Control+Enter')
  await expect(edit).toBeHidden()
  expect(b1.patches).toEqual(['Sửa\nX'])
})

test('note failures and late ACK retain revised add/edit drafts, including return to the original text', async ({ page, b1 }) => {
  await note(page)
  b1.failNote = true
  const add = page.getByTestId('note-item-add-input')
  await add.fill('Thử lại')
  await add.press('Control+Enter')
  await expect(page.getByTestId('note-detail-dialog').getByText('Synthetic note save failure', { exact: true })).toBeVisible()
  await expect(add).toHaveValue('Thử lại')
  b1.failNote = false
  let release!: () => void
  b1.holdNote = new Promise(resolve => { release = resolve })
  await add.press('Control+Enter')
  await expect.poll(() => b1.creates.length).toBe(2)
  await add.fill('Thử lại mới')
  await add.fill('Thử lại')
  release()
  await expect(page.getByTestId('note-item-add-submit')).toBeEnabled()
  await expect(add).toHaveValue('Thử lại')
  b1.holdNote = null
  await page.getByTestId('note-item-edit').first().click()
  const edit = page.getByTestId('note-item-edit-input')
  await edit.fill('Nội dung A')
  b1.holdNote = new Promise(resolve => { release = resolve })
  await edit.press('Control+Enter')
  await expect.poll(() => b1.patches.length).toBe(1)
  await edit.fill('Nội dung B')
  await edit.fill('Nội dung A')
  release()
  await expect(page.getByTestId('note-item-edit-save')).toBeEnabled()
  await expect(edit).toHaveValue('Nội dung A')
})

test('unknown retry keeps exact original body/client and late ACK retains newer text/reasons', async ({ page, b1 }) => {
  await page.goto('/')
  await positive(page)
  await input(page).fill('Bản gửi ban đầu')
  b1.failFeedback = true
  await page.getByTestId('mimi-positive-submit').click()
  await expect(supplement(page).getByRole('alert')).toBeVisible()
  const original = b1.feedback[1]
  await input(page).fill('Bản nháp mới')
  await supplement(page).getByRole('button', { name: 'Rõ ràng', exact: true }).click()
  b1.failFeedback = false
  let release!: () => void
  b1.holdFeedback = new Promise(resolve => { release = resolve })
  await page.getByTestId('mimi-positive-submit').click()
  await expect.poll(() => b1.feedback.length).toBe(3)
  expect(b1.feedback[2]).toEqual(original)
  await input(page).fill('Bản mới khi đang chờ')
  await page.getByTestId('mimi-positive-submit').dispatchEvent('submit')
  expect(b1.feedback).toHaveLength(3)
  release()
  await expect(page.getByTestId('mimi-positive-submit')).toHaveText('Gửi bổ sung')
  await expect(input(page)).toHaveValue('Bản mới khi đang chờ')
  await expect(supplement(page).getByRole('button', { name: 'Rõ ràng', exact: true })).toHaveAttribute('aria-pressed', 'true')
})

test('wrong ACK remains unknown, close/reopen and target changes preserve only the matching draft', async ({ page, b1 }) => {
  await page.goto('/')
  await positive(page)
  await input(page).fill('Bản nháp target một')
  b1.wrongAck = true
  await page.getByTestId('mimi-positive-submit').click()
  await expect(supplement(page).getByRole('alert')).toBeVisible()
  await supplement(page).getByRole('button', { name: 'Để sau', exact: true }).click()
  b1.wrongAck = false
  await positive(page, 1)
  await expect(input(page)).toHaveValue('')
  await input(page).fill('Bản nháp target hai')
  await supplement(page).getByRole('button', { name: 'Để sau', exact: true }).click()
  await positive(page, 0)
  await expect(input(page)).toHaveValue('Bản nháp target một')
  await expect(page.getByTestId('mimi-positive-submit')).toHaveText('Thử lại góp ý đã gửi')
  await page.getByTestId('mimi-positive-submit').click()
  await expect(input(page)).toHaveValue('')
  expect(b1.feedback.at(-1)?.target_id).toBe('01990000-0000-7000-8000-000000000101-answer-1')
})

test('Chromium composition trace commits Vietnamese without rewriting or unintended checklist submits', async ({ page, b1 }, info) => {
  await note(page)
  const cdp = await page.context().newCDPSession(page)
  const add = page.getByTestId('note-item-add-input')
  await add.fill('')
  await add.focus()
  await cdp.send('Input.imeSetComposition', { text: 'tiế', selectionStart: 3, selectionEnd: 3 })
  await add.press('Control+Enter')
  await expect(page.getByTestId('note-item-add-submit')).toBeEnabled()
  expect(b1.creates).toHaveLength(0)
  await cdp.send('Input.insertText', { text: 'tiếng Việt' })
  await expect(add).toHaveValue('tiếng Việt')
  await page.keyboard.press('Escape')
  await positive(page)
  const trace: unknown[] = []
  await page.exposeFunction('b1Trace', (value: unknown) => trace.push(value))
  await input(page).evaluate(node => {
    for (const type of ['beforeinput', 'input', 'compositionstart', 'compositionupdate', 'compositionend']) node.addEventListener(type, event => {
      const el = event.target as HTMLTextAreaElement
      const value = { type, value: el.value, start: el.selectionStart, end: el.selectionEnd, isComposing: (event as InputEvent).isComposing, inputType: (event as InputEvent).inputType }
      void (window as unknown as { b1Trace: (value: unknown) => Promise<void> }).b1Trace(value)
    })
  })
  await input(page).fill('abcd')
  await input(page).evaluate((node: HTMLTextAreaElement) => node.setSelectionRange(2, 2))
  await cdp.send('Input.imeSetComposition', { text: 'tiế', selectionStart: 3, selectionEnd: 3 })
  await expect(input(page)).toHaveValue('abtiếcd')
  await expect(page.getByTestId('mimi-positive-submit')).toBeDisabled()
  await cdp.send('Input.insertText', { text: 'tiếng Việt' })
  await expect(input(page)).toHaveValue('abtiếng Việtcd')
  expect((await position(input(page))).start).toBe(12)
  await input(page).fill('x'.repeat(7999))
  await cdp.send('Input.imeSetComposition', { text: 'tiế', selectionStart: 3, selectionEnd: 3 })
  await expect(input(page)).toHaveValue('x'.repeat(7999) + 'tiế')
  await cdp.send('Input.insertText', { text: 'ệ' })
  await expect(input(page)).toHaveValue('x'.repeat(7999) + 'ệ')
  await expect(page.getByTestId('mimi-positive-count')).toHaveText('8.000/8.000')
  await info.attach('chromium-composition-trace', { body: JSON.stringify(trace), contentType: 'application/json' })
  expect(trace.some(value => (value as { type: string }).type === 'compositionstart')).toBe(true)
  await cdp.detach()
})

test('pending old target ACK cannot erase drafts for another turn or conversation; reload drops memory-only drafts', async ({ page, b1 }, info) => {
  test.skip(info.project.name !== 'desktop', 'Conversation rail lifecycle uses desktop; turn lifecycle and close/reopen run on both viewports.')
  await page.goto('/')
  await positive(page)
  await input(page).fill('Target cũ đang chờ')
  let release!: () => void
  b1.holdFeedback = new Promise(resolve => { release = resolve })
  await page.getByTestId('mimi-positive-submit').click()
  await expect.poll(() => b1.feedback.length).toBe(2)
  await input(page).fill('Draft mới target cũ')
  await supplement(page).getByRole('button', { name: 'Để sau', exact: true }).click()
  await positive(page, 1)
  await input(page).fill('Draft turn thứ hai')
  await supplement(page).getByRole('button', { name: 'Để sau', exact: true }).click()
  await page.getByRole('button', { name: 'Hội thoại thứ hai', exact: false }).first().click()
  await positive(page)
  await expect(input(page)).toHaveValue('')
  await input(page).fill('Draft hội thoại khác')
  release()
  await expect(input(page)).toHaveValue('Draft hội thoại khác')
  await supplement(page).getByRole('button', { name: 'Để sau', exact: true }).click()
  await page.getByRole('button', { name: 'Hội thoại tổng hợp', exact: false }).first().click()
  await positive(page)
  await expect(input(page)).toHaveValue('Draft mới target cũ')
  await expect(page.getByTestId('mimi-positive-submit')).toHaveText('Gửi bổ sung')
  await page.reload()
  await positive(page)
  await expect(input(page)).toHaveValue('')
})
