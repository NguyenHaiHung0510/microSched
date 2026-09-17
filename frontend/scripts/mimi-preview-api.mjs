import { createServer } from 'node:http'
import { randomUUID } from 'node:crypto'

const HOST = '127.0.0.1'
const PORT = 8058
const conversationId = '01990000-0000-7000-8000-000000000058'
const now = () => new Date().toISOString()
const emptyPage = () => ({ items: [], next_cursor: null })

let conversation = null

function send(response, status, body) {
  response.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  })
  response.end(body === undefined ? '' : JSON.stringify(body))
}

async function readJson(request) {
  const chunks = []
  for await (const chunk of request) chunks.push(chunk)
  const raw = Buffer.concat(chunks).toString('utf8')
  return raw ? JSON.parse(raw) : {}
}

function newConversation() {
  return {
    id: conversationId,
    sensitivity: 'standard',
    generation: 1,
    messages: [],
    runs: [],
    change_sets: [],
    receipts: [],
    events: [],
    feedback: [],
  }
}

function previewTask(title) {
  const runId = randomUUID()
  const changeSetId = randomUUID()
  const timestamp = now()
  conversation = {
    ...conversation,
    generation: conversation.generation + 1,
    messages: [
      ...conversation.messages,
      { id: randomUUID(), run_id: runId, client_id: randomUUID(), sequence: conversation.messages.length + 1, role: 'user', content: title, created_at: timestamp },
      { id: randomUUID(), run_id: runId, client_id: null, sequence: conversation.messages.length + 2, role: 'assistant', content: 'Mình đã chuẩn bị một preview an toàn. Hãy kiểm tra trước khi xác nhận.', created_at: timestamp },
    ],
    runs: [...conversation.runs, { id: runId, generation: conversation.generation, state: 'awaiting_confirmation', provider_outcome: 'succeeded', deadline: new Date(Date.now() + 15 * 60_000).toISOString(), error_code: null, created_at: timestamp, completed_at: null }],
    change_sets: [...conversation.change_sets, {
      id: changeSetId,
      run_id: runId,
      state: 'pending',
      digest: 'a'.repeat(64),
      nonce: randomUUID(),
      expires_at: new Date(Date.now() + 15 * 60_000).toISOString(),
      policy_version: 'task-058-preview',
      operation: {
        operation_id: randomUUID(),
        tool: 'task.create.v1',
        args: { id: randomUUID(), title: title.slice(0, 200), body_md: null, status: 'open', priority: 'p1', due_precision: 'none', due_on: null, due_at: null, is_private: false, items: ['Kiểm tra receipt'] },
      },
    }],
  }
  return conversation
}

function taskRows(url) {
  const timestamp = now()
  const tasks = [
    { id: 'preview-task-1', title: 'Chuẩn bị duyệt UI Mimi', body_md: 'Dữ liệu synthetic cho preview Task 058.', status: 'open', priority: 'p1', due_precision: 'none', due_on: null, due_at: null, is_private: false, pinned: true, items: [], created_at: timestamp, updated_at: timestamp },
    { id: 'preview-task-2', title: 'Kiểm tra side-chat khi đổi tab', body_md: null, status: 'open', priority: 'p2', due_precision: 'none', due_on: null, due_at: null, is_private: false, pinned: false, items: [], created_at: timestamp, updated_at: timestamp },
  ]
  if (url.pathname.endsWith('/timeline')) {
    return { items: tasks, next_cursor: null, bucket_cursors: { overdue: null, dated: null, undated: null }, has_previous: false, has_next: false, loaded_range_start: timestamp.slice(0, 10), loaded_range_end: timestamp.slice(0, 10), counts: { overdue: 0, dated: 0, undated: 2 } }
  }
  return { items: tasks, next_cursor: null, has_previous: false, has_next: false }
}

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url ?? '/', `http://${HOST}:${PORT}`)
    const { pathname } = url
    const method = request.method ?? 'GET'

    if (pathname === '/api/me' && method === 'GET') {
      send(response, 200, { email: 'owner-preview@example.test', signed_in_at: now(), expires_at: new Date(Date.now() + 86_400_000).toISOString(), private_until: null, private_locked_until: null, pin_is_set: true, pin_is_bootstrap: false, mimi_available: true })
      return
    }
    if (pathname === '/api/mimi/conversations/current' && method === 'GET') {
      send(response, 200, conversation)
      return
    }
    if (pathname === '/api/mimi/conversations' && method === 'POST') {
      conversation ??= newConversation()
      send(response, 201, conversation)
      return
    }
    if (/^\/api\/mimi\/conversations\/[^/]+\/messages$/.test(pathname) && method === 'POST') {
      conversation ??= newConversation()
      const body = await readJson(request)
      send(response, 200, previewTask(String(body.content ?? 'Task preview synthetic')))
      return
    }
    if (/^\/api\/mimi\/change-sets\/[^/]+\/decision$/.test(pathname) && method === 'POST') {
      const body = await readJson(request)
      const pending = [...conversation.change_sets].reverse().find((item) => item.state === 'pending')
      if (!pending) {
        send(response, 409, { detail: 'Preview không còn chờ xác nhận.' })
        return
      }
      if (body.decision === 'reject') {
        conversation = { ...conversation, change_sets: conversation.change_sets.map((item) => item.id === pending.id ? { ...item, state: 'rejected' } : item) }
        send(response, 200, { change_set_id: pending.id, state: 'rejected' })
        return
      }
      const receipt = { id: randomUUID(), change_set_id: pending.id, operation_id: pending.operation.operation_id, task_id: pending.operation.args.id, digest: pending.digest, result: { task_id: pending.operation.args.id }, executed_at: now() }
      conversation = { ...conversation, runs: conversation.runs.map((run) => run.id === pending.run_id ? { ...run, state: 'completed', completed_at: now() } : run), change_sets: conversation.change_sets.map((item) => item.id === pending.id ? { ...item, state: 'executed' } : item), receipts: [...conversation.receipts, receipt] }
      send(response, 200, receipt)
      return
    }
    if (/^\/api\/mimi\/conversations\/[^/]+\/feedback$/.test(pathname) && method === 'POST') {
      const body = await readJson(request)
      const feedback = { id: randomUUID(), client_id: body.client_id, target_type: body.target_type, target_id: body.target_id, state: 'new', unresolved: true, created_at: now() }
      conversation = { ...conversation, feedback: [...conversation.feedback, feedback] }
      send(response, 201, feedback)
      return
    }
    if (pathname.startsWith('/api/tasks') && method === 'GET') {
      send(response, 200, taskRows(url))
      return
    }
    if (pathname === '/api/tracker/dashboard' && method === 'GET') {
      const month = url.searchParams.get('month') ?? now().slice(0, 7)
      const months = Number(url.searchParams.get('months') ?? 1)
      send(response, 200, { period_start: `${month}-01`, period_end: `${month}-28`, current_period_days: 28, prev_period_days: 28, prev_period_truncated: false, corrupted_entry_count: 0, f1_total: 0, f2_current: 0, f2_previous: 0, report_months: months, previous_period_start: null, previous_period_end: null, finance_months: [], activity_month: month, activity_days: [], f3_groups: [], f4_top: [], f5_net: 0, a2_gap: [], a3_counts: { week: 0, month: 0, year: 0 }, a4_trend: { current_month: 0, prev_avg: 0, trend: 'flat' }, f6: { monthly_burn: 0, subscription_count: 0, upcoming: [], corrupted_subscription_count: 0 } })
      return
    }
    if (pathname === '/api/reminders/device-status') {
      send(response, 200, { registered_devices: 0 })
      return
    }
    if (pathname.startsWith('/api/reminders')) {
      send(response, 200, { items: [], has_more: false })
      return
    }
    if (pathname.startsWith('/api/notes') || pathname.startsWith('/api/tracker/') || pathname.startsWith('/api/subscriptions') || pathname.startsWith('/api/settings') || pathname.startsWith('/api/calendar/')) {
      send(response, 200, emptyPage())
      return
    }
    if (pathname === '/auth/logout' && method === 'POST') {
      send(response, 204)
      return
    }
    send(response, 404, { detail: 'Task 058 preview route not implemented' })
  } catch (error) {
    send(response, 500, { detail: error instanceof Error ? error.message : 'Preview API failed' })
  }
})

server.listen(PORT, HOST, () => {
  process.stdout.write(`Task 058 synthetic preview API: http://${HOST}:${PORT}\n`)
})
