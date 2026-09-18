import { createServer } from 'node:http'
import { randomUUID } from 'node:crypto'

const HOST = '127.0.0.1'
const PORT = 8058
const conversationId = '01990000-0000-7000-8000-000000000058'
const now = () => new Date().toISOString()
const emptyPage = () => ({ items: [], next_cursor: null })

let conversation = null
let previewScenario = 'healthy'
let scenarioStartedAt = Date.now()
let previewConversations = [
  { id: conversationId, title: 'Chuẩn bị slide báo cáo Mimi P1', updated_at: now(), archived_at: null, metadata_version: 1, title_source: 'auto', title_locked: false, latest_run_state: 'completed' },
  { id: '01990000-0000-7000-8000-000000000059', title: 'Rà soát lịch học, deadline và ba phương án tránh xung đột trong tuần tới', updated_at: new Date(Date.now() - 3_600_000).toISOString(), archived_at: null, metadata_version: 2, title_source: 'owner', title_locked: true, latest_run_state: 'completed' },
  { id: '01990000-0000-7000-8000-000000000060', title: 'Tổng duyệt demo Mimi và kiểm tra receipt', updated_at: new Date(Date.now() - 86_400_000).toISOString(), archived_at: null, metadata_version: 1, title_source: 'auto', title_locked: false, latest_run_state: 'waiting_confirmation' },
  { id: '01990000-0000-7000-8000-000000000061', title: 'Hội thoại đã lưu trữ', updated_at: new Date(Date.now() - 12 * 86_400_000).toISOString(), archived_at: new Date(Date.now() - 10 * 86_400_000).toISOString(), metadata_version: 2, title_source: 'owner', title_locked: true, latest_run_state: 'completed' },
]

const scenarios = [
  { id: 'healthy', label: 'Ngày bình thường', description: 'Route ổn định, cache tốt và các run kết thúc sạch.' },
  { id: 'long_run', label: 'Run dài đang chạy', description: 'Hiển thị elapsed time, reasoning công khai và tool progress.' },
  { id: 'degraded', label: 'Provider suy giảm', description: 'Cache/uptime giảm, route phục hồi và diagnostics có ngữ cảnh.' },
  { id: 'owner_queue', label: 'Đang chờ Owner', description: 'Preview, feedback và hội thoại dài/archived cùng xuất hiện.' },
]

const rangeDays = { today: 1, '7d': 7, '30d': 30, week: 7, month: 30, quarter: 91, year: 365 }

function compactPoints(range, dailyCost, requestsPerDay, cacheBase) {
  const days = rangeDays[range] ?? 7
  const pointCount = days <= 7 ? days : days <= 30 ? 10 : 12
  return Array.from({ length: pointCount }, (_, index) => {
    const wave = 0.78 + ((index * 7) % 5) * 0.09
    return {
      label: days === 1 ? 'Hôm nay' : `${Math.max(1, Math.round(((index + 1) * days) / pointCount))}d`,
      cost: Number((dailyCost * days / pointCount * wave).toFixed(3)),
      requests: Math.max(1, Math.round(requestsPerDay * days / pointCount * wave)),
      cache_hit_rate: Number(Math.max(0, Math.min(99.9, cacheBase + ((index % 3) - 1) * 1.7)).toFixed(1)),
    }
  })
}

function previewState(range = '7d') {
  const safeRange = Object.hasOwn(rangeDays, range) ? range : '7d'
  const days = rangeDays[safeRange]
  const degraded = previewScenario === 'degraded'
  const dailyCost = degraded ? 0.42 : 0.093
  const requestsPerDay = degraded ? 76 : 118
  const cacheRate = degraded ? 61.4 : 94.2
  const running = previewScenario === 'long_run'
  const ownerQueue = previewScenario === 'owner_queue'
  const acceptedAt = running ? scenarioStartedAt - 4 * 60_000 - 37_000 : scenarioStartedAt - 18 * 60_000
  const deadlineAt = acceptedAt + 30 * 60_000

  return {
    synthetic: true,
    scenario: previewScenario,
    scenarios,
    checked_at: now(),
    usage: {
      range: safeRange,
      available_ranges: ['today', '7d', '30d', 'week', 'month', 'quarter', 'year'],
      cost: Number((dailyCost * days).toFixed(2)),
      requests: Math.round(requestsPerDay * days),
      total_tokens: Math.round(12_400_000 * days),
      cached_tokens: Math.round(12_400_000 * days * cacheRate / 100),
      cache_hit_rate: cacheRate,
      source: 'Synthetic · mô phỏng số liệu trực tiếp từ bên mua API',
      points: compactPoints(safeRange, dailyCost, requestsPerDay, cacheRate),
    },
    route: {
      model: 'DeepSeek V4 Flash 0731',
      provider: degraded ? 'Eligible pool · đang phục hồi' : 'Relace · synthetic',
      mode: 'Adaptive local dogfood',
      uptime_30d: degraded ? 82.7 : 97.8,
      median_ttft_ms: degraded ? 4200 : 680,
      privacy: 'ZDR · data collection deny',
    },
    run: {
      id: `run-${previewScenario}-058`,
      state: running ? 'running' : degraded ? 'recovering' : ownerQueue ? 'awaiting_owner' : 'completed',
      accepted_at: new Date(acceptedAt).toISOString(),
      deadline: new Date(deadlineAt).toISOString(),
      stage: running ? 'Đang sắp xếp lịch và kiểm tra xung đột' : degraded ? 'Đang đối soát provider trước khi tiếp tục' : ownerQueue ? 'Chờ bạn duyệt preview' : 'Đã hoàn tất và lưu receipt',
      summary: running ? 'Mimi vẫn làm việc ở server; đóng side-chat hoặc đổi hội thoại không làm dừng run.' : degraded ? 'Kết nối stream đã rớt. Mimi giữ nguyên run ID và chưa gửi lại request.' : ownerQueue ? 'Có một thay đổi an toàn đang chờ xác nhận; chưa ghi Task.' : 'Run kết thúc đúng một lần, không còn hành động chờ.',
      reasoning: running
        ? ['Đã đọc 14 Task STANDARD liên quan.', 'Phát hiện hai khung giờ có xung đột.', 'Đang so sánh phương án ít làm xáo trộn lịch nhất.']
        : degraded
          ? ['Provider outcome hiện chưa chắc chắn.', 'Đang reconcile cùng run ID trước khi cho phép resume.']
          : ['Đã kiểm tra scope STANDARD.', 'Không có write nào ngoài preview đã duyệt.'],
      tools: running
        ? [{ label: 'Đọc Task liên quan', state: 'done' }, { label: 'Kiểm tra lịch', state: 'done' }, { label: 'Xếp phương án', state: 'running' }, { label: 'Tạo preview', state: 'waiting' }]
        : degraded
          ? [{ label: 'Provider stream', state: 'done' }, { label: 'Reconcile outcome', state: 'running' }, { label: 'Tiếp tục run', state: 'waiting' }]
          : [{ label: 'Đọc dữ liệu', state: 'done' }, { label: 'Kiểm tra policy', state: 'done' }, { label: 'Lưu receipt', state: 'done' }],
      resumable: degraded,
    },
    attention: {
      pending_approvals: ownerQueue ? 2 : 0,
      unresolved_feedback: ownerQueue ? 3 : 0,
      incidents: degraded ? 1 : 0,
    },
    health: [
      { label: 'microSched API', state: 'good', detail: 'Sẵn sàng · vừa kiểm tra' },
      { label: 'Database', state: running ? 'good' : 'idle', detail: running ? 'Đang dùng cho checkpoint có ý nghĩa' : 'Không có keepalive · có thể idle tự nhiên' },
      { label: 'Provider route', state: degraded ? 'warning' : 'good', detail: degraded ? 'Stream gián đoạn · đang reconcile' : 'Trong eligible pool' },
      { label: 'Cache', state: degraded ? 'bad' : 'good', detail: `${cacheRate}% hit rate trong khoảng đang xem` },
    ],
    conversations: previewConversations.map((item) => ({ ...item, archived: Boolean(item.archived_at), unread: running && item.id === conversationId, state: item.archived_at ? 'Đã lưu trữ' : ownerQueue ? 'Chờ duyệt' : item.latest_run_state === 'completed' ? 'Đã xong' : 'Sẵn sàng' })),
  }
}

function conversationForScenario() {
  const base = newConversation()
  const timestamp = now()
  const run = previewState('7d').run
  const runRow = {
    id: run.id,
    generation: 1,
    state: run.state,
    provider_outcome: run.state === 'completed' ? 'succeeded' : run.state === 'recovering' ? 'unknown' : null,
    deadline: run.deadline,
    error_code: run.state === 'recovering' ? 'transport_disconnected' : null,
    created_at: run.accepted_at,
    completed_at: run.state === 'completed' ? timestamp : null,
  }
  return {
    ...base,
    messages: [
      { id: randomUUID(), run_id: run.id, client_id: randomUUID(), sequence: 1, role: 'user', content: previewScenario === 'long_run' ? 'Sắp xếp lại lịch tuần tới, giữ nguyên ba deadline quan trọng.' : 'Kiểm tra trạng thái Mimi hôm nay.', created_at: run.accepted_at },
      { id: randomUUID(), run_id: run.id, client_id: null, sequence: 2, role: 'assistant', content: run.summary, created_at: timestamp },
    ],
    runs: [runRow],
    events: [
      { id: randomUUID(), run_id: run.id, sequence: 1, kind: 'run.accepted', payload: {}, created_at: run.accepted_at },
      ...run.tools.map((tool, index) => ({ id: randomUUID(), run_id: run.id, sequence: index + 2, kind: `tool.${tool.state}`, payload: { label: tool.label }, created_at: timestamp })),
    ],
  }
}

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

function newConversation(id = conversationId, title = 'Hội thoại mới') {
  return {
    id,
    sensitivity: 'standard',
    title,
    title_source: 'auto',
    title_locked: false,
    metadata_version: 1,
    archived_at: null,
    updated_at: now(),
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

conversation = conversationForScenario()

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
    if (pathname === '/api/mimi/conversations' && method === 'GET') {
      const state = url.searchParams.get('state') ?? 'active'
      const items = previewConversations.filter((item) => state === 'all' || (state === 'archived') === Boolean(item.archived_at))
      send(response, 200, { items, next_cursor: null })
      return
    }
    if (pathname === '/api/mimi/preview' && method === 'GET') {
      send(response, 200, previewState(url.searchParams.get('range') ?? '7d'))
      return
    }
    if (pathname === '/api/mimi/preview/scenario' && method === 'POST') {
      const body = await readJson(request)
      if (!scenarios.some((item) => item.id === body.scenario)) {
        send(response, 422, { detail: 'Synthetic scenario không hợp lệ.' })
        return
      }
      previewScenario = body.scenario
      scenarioStartedAt = Date.now()
      conversation = conversationForScenario()
      send(response, 200, previewState('7d'))
      return
    }
    if (pathname === '/api/mimi/conversations' && method === 'POST') {
      const id = randomUUID()
      const title = `Hội thoại mới · ${new Date().toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' })}`
      const summary = { id, sensitivity: 'standard', title, title_source: 'auto', title_locked: false, generation: 1, metadata_version: 1, archived_at: null, updated_at: now(), latest_run_state: null }
      previewConversations = [summary, ...previewConversations]
      conversation = newConversation(id, title)
      send(response, 201, summary)
      return
    }
    if (/^\/api\/mimi\/conversations\/[^/]+$/.test(pathname) && method === 'GET') {
      const id = pathname.split('/').at(-1)
      const summary = previewConversations.find((item) => item.id === id)
      send(response, summary ? 200 : 404, summary ? { ...conversation, ...summary } : { detail: 'Mimi resource not found' })
      return
    }
    if (/^\/api\/mimi\/conversations\/[^/]+$/.test(pathname) && method === 'PATCH') {
      const id = pathname.split('/').at(-1)
      const body = await readJson(request)
      const index = previewConversations.findIndex((item) => item.id === id)
      if (index < 0) { send(response, 404, { detail: 'Mimi resource not found' }); return }
      previewConversations[index] = { ...previewConversations[index], title: String(body.title).trim().slice(0, 80), title_source: 'owner', title_locked: true, metadata_version: previewConversations[index].metadata_version + 1, updated_at: now() }
      send(response, 200, previewConversations[index])
      return
    }
    if (/^\/api\/mimi\/conversations\/[^/]+\/(archive|restore)$/.test(pathname) && method === 'POST') {
      const parts = pathname.split('/')
      const id = parts.at(-2)
      const archived = parts.at(-1) === 'archive'
      const index = previewConversations.findIndex((item) => item.id === id)
      if (index < 0) { send(response, 404, { detail: 'Mimi resource not found' }); return }
      previewConversations[index] = { ...previewConversations[index], archived_at: archived ? now() : null, metadata_version: previewConversations[index].metadata_version + 1, updated_at: now() }
      send(response, 200, previewConversations[index])
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
