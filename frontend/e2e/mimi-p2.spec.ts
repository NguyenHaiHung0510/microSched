import { test, expect } from './fixtures/tasks'
import { createServer, type ServerResponse } from 'node:http'
import type { MimiConversation, MimiConversationMetrics, MimiCollectionPlan } from '../src/mimi-api'

const cid = '01990000-0000-7000-8000-000000000201'
const rid = '01990000-0000-7000-8000-000000000202'
const now = '2026-10-18T10:00:00Z'
const metric = (known: number) => ({ known, observed: 1, missing: 0, complete: true })
const accounting: MimiConversationMetrics = {
  version: 1, scope: 'all_retained_conversation_receipts', scope_complete: true,
  scope_start: now, as_of: now, provenance: 'synthetic_server_receipts', retention: 'existing',
  reused_calls: 1, eligible_dispatches: 2,
  last_measured_input: { tokens: 64000, as_of: now, state: 'last_measured_current_projection_pending' },
  input: metric(320000), output: metric(48000), reasoning: metric(36000),
  usd: { known: '0.042700001', observed: 1, missing: 1, complete: false },
  cache: { cached: 96000, sample_input: 320000, ratio: 0.3, observed: 1, missing: 1, complete: false },
  purpose_counts: { main: 1, helper: 1, unclassified: 0 }, anomaly_dispatches: 0,
  effective_completion_per_second: null, responses: [],
}
function conversation(): MimiConversation {
  return { id: cid, sensitivity: 'standard', title: 'P2 kiểm tra ế ữ ộ 🌸', generation: 1,
    messages: [{ id: 'assistant-initial', run_id: 'old-run', client_id: null, sequence: 1,
      role: 'assistant', content: 'Mình sẵn sàng giúp bạn.', created_at: now }],
    runs: [], events: [], feedback: [], change_sets: [], receipts: [], metrics: accounting,
  }
}

for (const scenario of ['stats-composer', 'activity-stop', 'review'] as const) {
  test(`P2 ${scenario} synthetic full app`, async ({ page }, testInfo) => {
    let current = conversation()
    let posts = 0
    let confirms = 0
    let domainReads = 0
    let response: ServerResponse | undefined
    const server = createServer((request, result) => {
      result.setHeader('Access-Control-Allow-Origin', '*')
      result.setHeader('Access-Control-Allow-Headers', '*')
      if (request.method === 'OPTIONS') { result.writeHead(204); result.end(); return }
      result.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' })
      response = result
      result.write(`event: run.reserved\ndata: ${JSON.stringify({ run_id: rid })}\n\n`)
      result.write(`event: agent.executing_read_tools\ndata: ${JSON.stringify({ run_id: rid })}\n\n`)
      const receipt = { id: 'event-read', run_id: rid, sequence: 2, kind: 'tool.read_result', created_at: now,
        payload: { activity: { label: 'Đọc Task', state: 'recorded', query: {
          filter: { status: 'open', title_contains: 'mẫu' }, sort: 'updated_desc', limit: 20,
          projection: ['title', 'status'], cursor_present: false, has_next_page: false,
          count: 6, coverage: 'complete', as_of: now, error: null,
          intrinsic_provenance: ['source_version', 'collection_version'],
        } } } }
      current.events = [receipt]
      result.write(`event: tool.read_result\ndata: ${JSON.stringify(receipt)}\n\n`)
    })
    await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
    const address = server.address()
    const streamUrl = `http://127.0.0.1:${typeof address === 'object' && address ? address.port : 0}/stream`
    try {
      await page.route('**/api/me', route => route.fulfill({ json: {
        email: 'synthetic@example.test', signed_in_at: now, expires_at: '2099-01-01T00:00:00Z',
        private_until: null, private_locked_until: null, pin_is_set: true, pin_is_bootstrap: false, mimi_available: true,
      } }))
      await page.route(/\/api\/(notes|calendar|tracker)/, route => { domainReads++; return route.fulfill({ json: { items: [] } }) })
      await page.route('**/api/mimi/**', async route => {
        const req = route.request()
        const path = new URL(req.url()).pathname
        if (path.endsWith('/capabilities')) return route.fulfill({ json: {
          context_v1_enabled: true, live_provider_enabled: false, requested_model: 'synthetic/model',
          requested_effort: 'high', route_mode: 'native', model_selection_enabled: false,
          context_limit: 400000, output_reserve: 8192, policy_id: null, policy_sha256: null,
        } })
        if (path.endsWith('/operating-policy')) return route.fulfill({ json: { policy: { revision: 1, input_codepoints: 100, prices: {} }, applies_to: 'next_unsent_wire' } })
        if (path.endsWith('/metadata-warmup')) return route.fulfill({ json: { status: 'not_applicable', paid_calls: 0 } })
        if (path.endsWith('/conversations')) return route.fulfill({ json: { items: [{
          id: cid, sensitivity: 'standard', title: current.title, title_source: 'auto', title_locked: false,
          generation: 1, metadata_version: 1, archived_at: null, updated_at: now, latest_run_state: null,
        }], next_cursor: null } })
        if (path.endsWith('/messages/stream')) {
          posts++
          current.messages.push({ id: 'user-new', run_id: rid, client_id: 'synthetic', sequence: 2, role: 'user', content: 'Đọc Task mẫu', created_at: now })
          current.runs = [{ id: rid, generation: 2, state: 'running', provider_outcome: null, deadline: '2099-01-01T00:00:00Z', error_code: null, created_at: now, completed_at: null }]
          return route.continue({ url: streamUrl })
        }
        if (path.endsWith('/cancel')) {
          current.runs = current.runs.map(run => ({ ...run, state: 'cancelled', provider_outcome: 'unknown' }))
          response?.write(`event: conversation.snapshot\ndata: ${JSON.stringify(current)}\n\n`)
          response?.end()
          return route.fulfill({ json: { run_id: rid, state: 'cancelled', provider_outcome: 'unknown', accepted: true } })
        }
        if (path.endsWith('/decision')) {
          confirms++
          expect(req.postDataJSON()).toEqual({ digest: 'synthetic', nonce: 'synthetic', decision: 'confirm' })
          expect(req.headers()['idempotency-key']).toBeTruthy()
          expect(current.change_sets[0].operation.tool === 'task.collection.v1' && current.change_sets[0].operation.args.entries.length).toBe(201)
          current.change_sets = current.change_sets.map(change => ({ ...change, state: 'executed' }))
          return route.fulfill({ json: { id: 'synthetic-receipt', change_set_id: 'change', operation_id: 'operation', task_id: null, digest: 'synthetic', result: { count: 201 }, executed_at: now } })
        }
        if (path.endsWith('/preview')) return route.fulfill({ status: 404, json: {} })
        return route.fulfill({ json: current })
      })
      if (scenario === 'review') {
        const plan: MimiCollectionPlan = { schema_version: 'mimi.task-collection.v1', entries: Array.from({ length: 201 }, (_, i) => ({
          id: `task-${i}`, command: { action: 'edit', expected_collection_version: 1, fields: { title: `Sau ${i}` }, children: [], reminder: { action: 'keep' } },
          before: { fields: { title: `Trước ${i}` }, children: [] }, after: { fields: { title: `Sau ${i}` }, children: [] }, reminder_effect: { action: 'keep' },
        })) }
        current.change_sets = [{ id: 'change', run_id: rid, state: 'pending', digest: 'synthetic', nonce: 'synthetic', expires_at: '2099-01-01T00:00:00Z', policy_version: 'synthetic', confirmation_preflight: { status: 'eligible', reason: null }, operation: { operation_id: 'operation', tool: 'task.collection.v1', args: plan } }]
        current.runs = [{ id: rid, generation: 1, state: 'waiting_confirmation', provider_outcome: 'succeeded', deadline: '2099-01-01T00:00:00Z', error_code: null, created_at: now, completed_at: now }]
      }
      await page.goto('/')
      await page.getByRole('tab', { name: 'Mimi', exact: true }).click()
      await expect(page.getByTestId('mimi-input')).toBeVisible()
      const input = page.getByTestId('mimi-input')
      if (scenario === 'stats-composer') {
        expect(domainReads).toBe(0)
        await expect(page.locator('#mimi-message-count')).toHaveCount(0)
        await expect(page.getByRole('button', { name: 'Xem lượt mới nhất' })).toHaveCount(0)
        const meter = page.getByTestId('mimi-run-context-inspector')
        await expect(meter.locator('xpath=..').getByTestId('mimi-route-settings')).toBeVisible()
        await meter.focus()
        const popover = page.getByRole('dialog', { name: 'Thống kê hội thoại' })
        await expect(popover).toBeVisible()
        const popText = await popover.getByTestId('mimi-metrics-summary').innerHTML()
        await expect(popover.getByTestId('mimi-metrics-responses')).not.toHaveAttribute('open', '')
        await page.keyboard.press('Escape')
        await meter.click()
        await expect(popover).toBeVisible()
        await expect(popover).not.toContainText('Bytes')
        await page.keyboard.press('Escape')
        const rail = page.getByTestId('mimi-context-rail').filter({ visible: true })
        if (!await rail.count()) await page.getByRole('button', { name: /^(Thống kê hội thoại|Thống kê và thông báo)$/ }).click()
        expect(await page.locator('[data-testid="mimi-context-rail"]:visible').getByTestId('mimi-metrics-summary').innerHTML()).toBe(popText)
        if ((page.viewportSize()?.width ?? 0) < 1024) await page.keyboard.press('Escape')
        await input.fill('🌸'.repeat(101))
        await expect(page.locator('#mimi-message-count')).toContainText('101 / 100')
        await expect(page.getByRole('button', { name: 'Gửi', exact: true })).toBeDisabled()
        await input.fill('Đang gõ tiếng Việt')
        await input.dispatchEvent('keydown', { key: 'Enter', code: 'Enter', isComposing: true })
        expect(posts).toBe(0)
        await expect(input).toHaveValue('Đang gõ tiếng Việt')
        await input.press('Shift+Enter')
        expect(posts).toBe(0)
      } else if (scenario === 'activity-stop') {
        await input.fill('Đọc Task mẫu')
        await input.press('Enter')
        const pending = page.getByTestId('mimi-pending-answer')
        await expect(pending).toBeVisible()
        await expect(pending.getByTestId('mimi-progress')).toBeVisible()
        await expect(pending.getByTestId('mimi-tool-activity')).toContainText('6 kết quả')
        await expect(pending.locator('details').last()).not.toHaveAttribute('open', '')
        await pending.getByText('Đọc Task · Đã ghi nhận · 6 kết quả', { exact: true }).click()
        await expect(pending).toContainText('Tiêu đề chứa: mẫu')
        // Only whole validated text appears after the canonical terminal snapshot.
        current.messages.push({ id: 'answer-final', run_id: rid, client_id: null, sequence: 3,
          role: 'assistant', content: 'Mình đã đọc đủ 6 Task mẫu.', created_at: now })
        current.runs = current.runs.map(run => ({ ...run, state: 'completed', provider_outcome: 'succeeded', completed_at: now }))
        response?.write(`event: conversation.snapshot\ndata: ${JSON.stringify(current)}\n\n`)
        response?.end()
        await expect(pending).toHaveCount(0)
        const answer = page.locator('article').filter({ hasText: 'Mình đã đọc đủ 6 Task mẫu.' })
        await expect(answer).toHaveCount(1)
        await expect(answer.getByTestId('mimi-tool-activity')).toContainText('6 kết quả')
        expect(posts).toBe(1)
        await input.fill('Đọc tiếp')
        await input.press('Enter')
        await expect(pending).toBeVisible()
        await pending.getByRole('button', { name: 'Huỷ run ngay' }).click()
        await expect(pending).toHaveCount(0)
        expect(posts).toBe(2)
      } else {
        await page.getByRole('button', { name: 'Xem và duyệt', exact: true }).click()
        const dialog = page.getByRole('dialog', { name: 'Duyệt toàn bộ 201 Task' })
        await expect(dialog.getByRole('columnheader', { name: 'Tiêu đề trước' })).toBeVisible()
        await expect(dialog.getByTestId('mimi-review-row')).toHaveCount(100)
        await expect(dialog.getByTestId('mimi-review-row').first()).toContainText('Trước 0')
        await dialog.getByRole('button', { name: 'Trang sau' }).click()
        await expect(dialog.getByTestId('mimi-review-row')).toHaveCount(100)
        await dialog.getByRole('button', { name: 'Trang sau' }).click()
        await expect(dialog.getByTestId('mimi-review-row')).toHaveCount(1)
        await dialog.getByRole('textbox', { name: 'Tìm trong preview' }).fill('Trước 0')
        await expect(dialog.getByTestId('mimi-review-row')).toHaveCount(1)
        await expect(dialog.getByRole('button', { name: 'Xác nhận toàn bộ 201 Task' })).toBeEnabled()
        expect(confirms).toBe(0)
        const scroll = await dialog.locator('table').evaluate(table => {
          const box = table.parentElement!; return { scroll: box.scrollHeight, height: box.clientHeight }
        })
        expect(scroll.height).toBeGreaterThan(0)
        await dialog.getByRole('button', { name: 'Xác nhận toàn bộ 201 Task' }).click()
        await expect.poll(() => confirms).toBe(1)
      }
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
      expect(overflow).toBe(false)
      const font = await input.evaluate(el => getComputedStyle(el).fontFamily)
      expect(font).toContain('Nunito')
      await page.mouse.move(0, 0)
      await page.screenshot({ path: testInfo.outputPath(`${scenario}.png`), fullPage: true })
    } finally {
      response?.end()
      server.closeAllConnections()
      await new Promise<void>(resolve => server.close(() => resolve()))
    }
  })
}
