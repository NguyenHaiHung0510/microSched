import { expect, test as base } from './tasks'

/**
 * Mock for the tracker slice (`/api/tracker/**`). It intentionally mirrors the
 * backend DTO shapes at the network boundary; everything else falls back to the
 * tasks fixture (session, private gate).
 */
export type FixtureTracker = {
  id: string
  name: string
  kind: 'health' | 'finance'
  direction: 'in' | 'out'
  input_mode: 'event' | 'money' | 'quantity'
  group_id: string | null
  unit: string | null
  color: string | null
  reminder_time: string | null
  reminder_text: string | null
  is_private: boolean
  last_entry_at: string | null
  entry_count_30d: number
  created_at: string
  updated_at: string
}

export type FixtureEntry = {
  id: string
  tracker_id: string
  occurred_at: string | null
  quantity: number | null
  amount: number | null
  list_amount: number | null
  note_md: string | null
  created_at: string
  updated_at: string
}

function nowIso(): string {
  return new Date().toISOString()
}

function tracker(overrides: Partial<FixtureTracker>): FixtureTracker {
  return {
    id: 'tracker-001',
    name: 'Hút thuốc',
    kind: 'health',
    direction: 'out',
    input_mode: 'event',
    group_id: null,
    unit: null,
    color: null,
    reminder_time: null,
    reminder_text: null,
    is_private: false,
    last_entry_at: new Date(Date.now() - 2 * 86_400_000).toISOString(),
    entry_count_30d: 3,
    created_at: nowIso(),
    updated_at: nowIso(),
    ...overrides,
  }
}

function entry(overrides: Partial<FixtureEntry>): FixtureEntry {
  return {
    id: `entry-${Date.now()}`,
    tracker_id: 'tracker-001',
    occurred_at: nowIso(),
    quantity: null,
    amount: null,
    list_amount: null,
    note_md: null,
    created_at: nowIso(),
    updated_at: nowIso(),
    ...overrides,
  }
}

export type TrackerApiState = {
  groups: Array<{ id: string; name: string; kind: string; tracker_count: number }>
  trackers: FixtureTracker[]
  entries: FixtureEntry[]
  counts: Record<string, number>
  count(method: string, path: string): number
}

export const test = base.extend<{ trackerApi: TrackerApiState }>({
  trackerApi: [
    async ({ page }, use) => {
      const state: TrackerApiState = {
        groups: [{ id: 'group-001', name: 'Sức khoẻ', kind: 'health', tracker_count: 1 }],
        trackers: [
          tracker({
            id: 'tracker-001',
            name: 'Hút thuốc',
            kind: 'health',
            input_mode: 'event',
            group_id: 'group-001',
            entry_count_30d: 3,
            last_entry_at: new Date(Date.now() - 2 * 86_400_000).toISOString(),
          }),
          tracker({
            id: 'tracker-002',
            name: 'Ăn uống',
            kind: 'finance',
            direction: 'out',
            input_mode: 'money',
            entry_count_30d: 1,
            last_entry_at: new Date(Date.now() - 2 * 3_600_000).toISOString(),
          }),
          tracker({
            id: 'tracker-003',
            name: 'Đọc sách',
            kind: 'health',
            input_mode: 'quantity',
            unit: 'phút',
            entry_count_30d: 0,
            last_entry_at: null,
          }),
        ],
        entries: [],
        counts: {},
        count(method, path) {
          return this.counts[`${method}:${path}`] ?? 0
        },
      }

      await page.route('**/api/tracker/**', async (route) => {
        const request = route.request()
        const method = request.method()
        const path = new URL(request.url()).pathname
        const key = `${method}:${path}`
        state.counts[key] = (state.counts[key] ?? 0) + 1

        if (path === '/api/tracker/groups' && method === 'GET') {
          await route.fulfill(jsonResponse({ items: state.groups }))
          return
        }
        if (path === '/api/tracker/groups' && method === 'POST') {
          const payload = JSON.parse(request.postData() ?? '{}') as {
            id?: string
            name: string
            kind: string
          }
          const created = {
            id: payload.id ?? `group-${Date.now()}`,
            name: payload.name,
            kind: payload.kind,
            color: null,
            position: state.groups.length,
            tracker_count: 0,
            created_at: nowIso(),
            updated_at: nowIso(),
          }
          state.groups.push(created)
          await route.fulfill(jsonResponse(created, 201))
          return
        }

        if (path === '/api/tracker/trackers' && method === 'GET') {
          await route.fulfill(jsonResponse({ items: state.trackers }))
          return
        }
        if (path === '/api/tracker/trackers' && method === 'POST') {
          const payload = JSON.parse(request.postData() ?? '{}') as Partial<FixtureTracker>
          const created = tracker({
            id: payload.id ?? `tracker-${Date.now()}`,
            name: payload.name ?? '',
            kind: payload.kind ?? 'health',
            input_mode: payload.input_mode ?? 'event',
            unit: payload.unit ?? null,
          })
          state.trackers.push(created)
          await route.fulfill(jsonResponse(created, 201))
          return
        }

        const trackerMatch = path.match(/^\/api\/tracker\/trackers\/([^/]+)$/)
        if (trackerMatch && method === 'DELETE') {
          state.trackers = state.trackers.filter((item) => item.id !== trackerMatch[1])
          await route.fulfill({ status: 204 })
          return
        }
        if (trackerMatch && method === 'PATCH') {
          const current = state.trackers.find((item) => item.id === trackerMatch[1])
          if (current) {
            const payload = JSON.parse(request.postData() ?? '{}') as Partial<FixtureTracker>
            Object.assign(current, payload, { updated_at: nowIso() })
          }
          await route.fulfill(jsonResponse(current ?? { status: 'missing' }, current ? 200 : 404))
          return
        }

        if (path === '/api/tracker/entries' && method === 'GET') {
          await route.fulfill(jsonResponse({ items: state.entries }))
          return
        }
        if (path === '/api/tracker/entries' && method === 'POST') {
          const payload = JSON.parse(request.postData() ?? '{}') as {
            id?: string
            tracker_id: string
            occurred_at?: string
            amount?: number
            quantity?: number
          }
          const created = entry({
            id: payload.id ?? `entry-${Date.now()}`,
            tracker_id: payload.tracker_id,
            occurred_at: payload.occurred_at ?? nowIso(),
            amount: payload.amount ?? null,
            quantity: payload.quantity ?? null,
          })
          state.entries.unshift(created)
          await route.fulfill(jsonResponse(created, 201))
          return
        }

        const entryMatch = path.match(/^\/api\/tracker\/entries\/([^/]+)$/)
        if (entryMatch && method === 'DELETE') {
          state.entries = state.entries.filter((item) => item.id !== entryMatch[1])
          await route.fulfill({ status: 204 })
          return
        }
        if (entryMatch && method === 'POST') {
          await route.fulfill(
            jsonResponse({ id: entryMatch[1], status: 'restored' }),
          )
          return
        }

        if (path === '/api/tracker/dashboard' && method === 'GET') {
          await route.fulfill(
            jsonResponse({
              period_start: nowIso(),
              period_end: nowIso(),
              current_period_days: 5,
              prev_period_days: 5,
              prev_period_truncated: false,
              corrupted_entry_count: 0,
              f1_total: 0,
              f2_current: 0,
              f2_previous: 0,
              f3_groups: [],
              f4_top: [],
              f5_net: 0,
              a2_gap: [],
              a3_counts: { week: 0, month: 0, year: 0 },
              a4_trend: { current_month: 0, prev_avg: 0, trend: 'flat' },
              f6: {
                monthly_burn: 0,
                subscription_count: 0,
                upcoming: [],
                corrupted_subscription_count: 0,
              },
            }),
          )
          return
        }

        await route.fallback()
      })

      await page.route('**/api/subscriptions**', async (route) => {
        const request = route.request()
        const method = request.method()
        const path = new URL(request.url()).pathname
        if (path === '/api/subscriptions' && method === 'GET') {
          await route.fulfill(jsonResponse({ items: [] }))
          return
        }
        await route.fulfill({ status: 404 })
      })

      await page.route('**/api/settings**', async (route) => {
        const request = route.request()
        const method = request.method()
        const path = new URL(request.url()).pathname
        if (path === '/api/settings' && method === 'GET') {
          await route.fulfill(
            jsonResponse({
              items: [
                { key: 'subscription_expiry_lead_days', value: 3 },
                { key: 'show_list_price', value: true },
              ],
            }),
          )
          return
        }
        await route.fulfill({ status: 404 })
      })
      await use(state)
    },
    { auto: true },
  ],
})

function jsonResponse(body: unknown, status = 200) {
  return {
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  }
}

export { expect }
