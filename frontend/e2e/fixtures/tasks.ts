import { test as base, expect } from '@playwright/test'

/**
 * This fixture mirrors backend/app/domain/tasks.py::TaskRead at the network
 * boundary. It is intentionally the only API fixture module: it can drift as
 * the API shape changes, so a future real-backend e2e lane must replace or
 * validate this fixture rather than silently inheriting stale data.
 */
export type FixtureTask = {
  id: string
  title: string
  body_md: string | null
  status: 'open' | 'completed'
  priority: 'p1' | 'p2' | 'p3' | null
  due_at: string | null
  is_private: boolean
  pinned: boolean
  items: Array<{
    id: string
    content: string
    is_completed: boolean
    position: number
  }>
  created_at: string
  updated_at: string
}

const past = (days: number) => new Date(Date.now() - days * 86_400_000).toISOString()
const future = (days: number) => new Date(Date.now() + days * 86_400_000).toISOString()
const privateWindow = () => new Date(Date.now() + 36 * 60_000).toISOString()

function randomPin(): string {
  return Array.from({ length: 6 }, () => Math.floor(Math.random() * 10)).join('')
}

export const fixturePrivatePin = randomPin()
export let fixtureWrongPin = randomPin()
while (fixtureWrongPin === fixturePrivatePin) fixtureWrongPin = randomPin()

const adversarialNoBreak = 'A'.repeat(70)
const adversarialVietnamese =
  'Đọc kỹ những việc cần làm, giữ nguyên dấu tiếng Việt dày đặc để kiểm tra xuống dòng và chiều cao thẻ; '
    .repeat(3)
    .slice(0, 150)

function item(id: string, content: string, isCompleted = false) {
  return { id, content, is_completed: isCompleted, position: 0 }
}

function task(
  id: string,
  title: string,
  options: Partial<FixtureTask> = {},
): FixtureTask {
  const timestamp = new Date().toISOString()
  return {
    id,
    title,
    body_md: null,
    status: 'open',
    priority: null,
    due_at: null,
    is_private: false,
    pinned: false,
    items: [],
    created_at: timestamp,
    updated_at: timestamp,
    ...options,
  }
}

/** Required QA data: hostile text, 30+ records, mixed status, and 3 scattered overdue records. */
export const fixtureTasks: FixtureTask[] = [
  task('task-001', 'Chuẩn bị kế hoạch tuần', { priority: 'p1', pinned: true }),
  task('task-002', 'Đã xong nhưng vẫn ghim', { status: 'completed', pinned: true }),
  task('task-003', 'Việc bình thường có emoji 🚲', { body_md: 'Ghi chú ngắn.' }),
  task('task-004', 'Việc trễ hạn thứ nhất', { due_at: past(4) }),
  task('task-005', adversarialNoBreak, {
    body_md: 'Ghi chú của một task có tiêu đề không có điểm ngắt.',
    items: [item('item-005', adversarialNoBreak)],
  }),
  task('task-006', 'CHỮ HOA CÓ DẤU', { priority: 'p2' }),
  task('task-007', '    ', { body_md: 'Nội dung fixture toàn khoảng trắng ở title.' }),
  task('task-008', 'X'),
  task('task-009', 'Task riêng tư', { is_private: true }),
  task('task-010', 'Đã hoàn thành không ghim', { status: 'completed' }),
  task('task-011', 'Việc kế tiếp', { due_at: future(2) }),
  task('task-012', 'Checklist nhiều mục', {
    items: [
      item('item-012-1', 'Mục đầu tiên', true),
      item('item-012-2', 'Mục thứ hai'),
      item('item-012-3', 'Mục thứ ba'),
      item('item-012-4', 'Mục thứ tư'),
    ],
  }),
  task('task-013', 'Học một điều mới', { priority: 'p3' }),
  task('task-014', 'Sắp xếp tài liệu'),
  task('task-015', 'Gọi điện'),
  task('task-016', 'Mua đồ dùng'),
  task('task-017', 'Việc trễ hạn thứ hai', { due_at: past(2) }),
  task('task-018', 'Đọc sách'),
  task('task-019', 'Đi bộ'),
  task('task-020', 'Viết nhật ký'),
  task('task-021', 'Kiểm tra lịch'),
  task('task-022', 'Lên thực đơn'),
  task('task-023', 'Dọn bàn làm việc'),
  task('task-024', 'Sao lưu dữ liệu'),
  task('task-025', 'Xem lại mục tiêu'),
  task('task-026', 'Tưới cây'),
  task('task-027', 'Đặt lịch hẹn'),
  task('task-028', 'Gửi tài liệu'),
  task('task-029', 'Việc trễ hạn thứ ba', { due_at: past(1) }),
  task('task-030', 'Chuẩn bị bữa sáng'),
  task('task-031', 'Đọc email công việc'),
  task('task-032', 'Thẻ cuối cùng để kiểm tooltip', {
    body_md: adversarialVietnamese,
    items: [item('item-032', 'Checklist cuối màn hình')],
  }),
]

export type TaskApiState = {
  tasks: FixtureTask[]
  sessionStatus: number
  privateUntil: string | null
  privateLockedUntil: string | null
  pinIsSet: boolean
  pinIsBootstrap: boolean
  wrongPinCount: number
  counts: Record<string, number>
  count(method: string, path: string): number
  resetCounts(): void
}

function cloneTasks() {
  return fixtureTasks.map((entry) => ({
    ...entry,
    items: entry.items.map((child) => ({ ...child })),
  }))
}

function jsonResponse(body: unknown, status = 200) {
  return {
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  }
}

export const test = base.extend<{ taskApi: TaskApiState }>({
  // `auto: true`: this mock must be live for every test regardless of whether
  // the test destructures `taskApi`. Without it, a test that forgets to name
  // the fixture silently gets a real, unmocked page — the app then calls the
  // vite-preview proxy for `/api/*`, which points at a backend that isn't
  // running in this e2e lane, and every request fails with ECONNREFUSED.
  taskApi: [async ({ page }, use) => {
    const state: TaskApiState = {
      tasks: cloneTasks(),
      sessionStatus: 200,
      privateUntil: privateWindow(),
      privateLockedUntil: null,
      pinIsSet: true,
      pinIsBootstrap: true,
      wrongPinCount: 0,
      counts: {},
      count(method, path) {
        return this.counts[`${method}:${path}`] ?? 0
      },
      resetCounts() {
        this.counts = {}
      },
    }

    await page.route('**/api/**', async (route) => {
      const request = route.request()
      const method = request.method()
      const url = new URL(request.url())
      const path = url.pathname
      const key = `${method}:${path}`
      state.counts[key] = (state.counts[key] ?? 0) + 1

      if (path === '/api/me') {
        if (state.sessionStatus !== 200) {
          await route.fulfill({ status: state.sessionStatus })
          return
        }
        await route.fulfill(
          jsonResponse({
            email: 'qa@example.test',
            signed_in_at: new Date().toISOString(),
            expires_at: future(30),
            private_until: state.privateUntil,
            private_locked_until: state.privateLockedUntil,
            pin_is_set: state.pinIsSet,
            pin_is_bootstrap: state.pinIsBootstrap,
          }),
        )
        return
      }

      if (path === '/api/private/unlock' && method === 'POST') {
        const now = Date.now()
        const lockedUntil = state.privateLockedUntil
          ? Date.parse(state.privateLockedUntil)
          : 0
        if (lockedUntil > now) {
          const retryAfterSeconds = Math.max(1, Math.ceil((lockedUntil - now) / 1000))
          await route.fulfill({
            ...jsonResponse(
              {
                detail: 'Đang khoá tạm',
                retry_after_seconds: retryAfterSeconds,
              },
              429,
            ),
            headers: { 'Retry-After': String(retryAfterSeconds) },
          })
          return
        }

        const payload = JSON.parse(request.postData() ?? '{}') as { pin?: string }
        if (payload.pin !== fixturePrivatePin) {
          state.wrongPinCount += 1
          if (state.wrongPinCount === 10) {
            state.privateLockedUntil = new Date(now + 5 * 60_000).toISOString()
            await route.fulfill({
              ...jsonResponse(
                {
                  detail: 'Đang khoá tạm',
                  retry_after_seconds: 300,
                },
                429,
              ),
              headers: { 'Retry-After': '300' },
            })
            return
          }
          await route.fulfill(
            jsonResponse(
              { detail: 'Sai PIN', remaining: 10 - state.wrongPinCount },
              401,
            ),
          )
          return
        }

        state.wrongPinCount = 0
        state.privateLockedUntil = null
        state.privateUntil = privateWindow()
        await route.fulfill(jsonResponse({ private_until: state.privateUntil }))
        return
      }

      if (path === '/api/private/lock' && method === 'POST') {
        state.privateUntil = null
        await route.fulfill({ status: 204 })
        return
      }

      if (path === '/api/private/pin' && method === 'POST') {
        state.pinIsSet = true
        state.pinIsBootstrap = false
        state.wrongPinCount = 0
        state.privateLockedUntil = null
        await route.fulfill({ status: 204 })
        return
      }

      if (path === '/api/tasks' && method === 'GET') {
        const privateOpen = Boolean(
          state.privateUntil && Date.parse(state.privateUntil) > Date.now(),
        )
        await route.fulfill(
          jsonResponse({
            items: state.tasks.filter((entry) => !entry.is_private || privateOpen),
          }),
        )
        return
      }

      if (path === '/api/tasks' && method === 'POST') {
        const payload = JSON.parse(request.postData() ?? '{}') as Partial<FixtureTask>
        const created = task(
          String(payload.id ?? `task-created-${Date.now()}`),
          String(payload.title ?? ''),
          {
            body_md: payload.body_md ?? null,
            priority: payload.priority ?? null,
            due_at: payload.due_at ?? null,
            is_private: payload.is_private ?? false,
          },
        )
        state.tasks.unshift(created)
        await route.fulfill(jsonResponse(created, 201))
        return
      }

      const taskMatch = path.match(/^\/api\/tasks\/([^/]+)$/)
      if (taskMatch && method === 'PATCH') {
        const current = state.tasks.find((entry) => entry.id === taskMatch[1])
        if (!current) {
          await route.fulfill({ status: 404 })
          return
        }
        const payload = JSON.parse(request.postData() ?? '{}') as Partial<FixtureTask>
        Object.assign(current, payload, { updated_at: new Date().toISOString() })
        await route.fulfill(jsonResponse(current))
        return
      }

      if (taskMatch && method === 'DELETE') {
        state.tasks = state.tasks.filter((entry) => entry.id !== taskMatch[1])
        await route.fulfill({ status: 204 })
        return
      }

      const itemMatch = path.match(/^\/api\/tasks\/([^/]+)\/items\/?([^/]*)$/)
      if (itemMatch) {
        const [, taskId, itemId] = itemMatch
        const owner = state.tasks.find((entry) => entry.id === taskId)
        if (!owner) {
          await route.fulfill({ status: 404 })
          return
        }

        if (method === 'POST' && !itemId) {
          const payload = JSON.parse(request.postData() ?? '{}') as {
            content?: string
            position?: number
          }
          const created = item(`item-created-${Date.now()}`, String(payload.content ?? ''))
          owner.items.push(created)
          await route.fulfill(jsonResponse(created, 201))
          return
        }

        if (method === 'PATCH' && itemId) {
          const target = owner.items.find((entry) => entry.id === itemId)
          if (!target) {
            await route.fulfill({ status: 404 })
            return
          }
          const payload = JSON.parse(request.postData() ?? '{}') as {
            is_completed?: boolean
          }
          Object.assign(target, payload)
          await route.fulfill(jsonResponse(target))
          return
        }

        if (method === 'DELETE' && itemId) {
          owner.items = owner.items.filter((entry) => entry.id !== itemId)
          await route.fulfill({ status: 204 })
          return
        }
      }

      // `fallback()`, not a hard 404: this handler only owns `/api/tasks*`
      // and `/api/me`. A future slice's fixture (notes, calendar, ...) may
      // register its own `**/api/**` route alongside this one — a hard 404
      // here would eat that request before its own handler ever saw it.
      await route.fallback()
    })

    await use(state)
  }, { auto: true }],
})

export { expect }
