import { type QueryClient, type QueryKey } from '@tanstack/react-query'
import type { Fields } from './protocol'

const families = new Set(['tasks', 'calendar', 'tracker', 'notes', 'subscription', 'subscriptions', 'reminders', 'reminder-history'])
export const isPrivateCapableFamily = (key: QueryKey) => families.has(String(key[0]))
const object = (value: unknown): value is Fields => !!value && typeof value === 'object' && !Array.isArray(value)

/** RAM-only masking. This never widens the separate public disk-cache allowlist. */
export function maskPrivateQueries(client: Pick<QueryClient, 'cancelQueries' | 'getQueryCache' | 'setQueryData' | 'removeQueries'>) {
  // The session request may itself be reporting 401; cancelling it here would
  // suppress the authoritative error and leave App waiting forever. Its private
  // response is already fenced by the sessionRequest visibility epoch.
  void client.cancelQueries({ predicate: q => isPrivateCapableFamily(q.queryKey) }, { revert: false })
  const queries = client.getQueryCache().getAll()
  const publicTrackers = new Set<string>()
  for (const query of queries) {
    if (query.queryKey[0] !== 'tracker' || query.queryKey[1] !== 'trackers') continue
    const data = query.state.data
    const rows = Array.isArray(data) ? data : object(data) && Array.isArray(data.items) ? data.items : []
    for (const row of rows) if (object(row) && row.is_private === false) publicTrackers.add(String(row.id))
  }
  for (const query of queries) {
    const key = query.queryKey
    if (key[0] === 'session' && object(query.state.data)) {
      client.setQueryData(key, { ...query.state.data, private_until: null }, { updatedAt: query.state.dataUpdatedAt })
      continue
    }
    if (!isPrivateCapableFamily(key)) continue
    const data = query.state.data
    const isEntry = key[0] === 'tracker' && key[1] === 'entries'
    const publicRow = (row: unknown) => object(row) && (isEntry
      ? publicTrackers.has(String(row.tracker_id)) : row.is_private === false)
    let safe: unknown
    if (Array.isArray(data)) safe = data.filter(publicRow)
    else if (object(data) && Array.isArray(data.items)) {
      // Old mixed-private totals and continuation cursors are not public facts.
      const rows = data.items.filter(publicRow)
      safe = { items: rows, next_cursor: null, has_more: false, snapshot_partial: true,
        ...(key[1] === 'timeline' ? { bucket_cursors: {overdue:null,dated:null,undated:null},
          bucket_counts: {overdue:0,dated:0,undated:0},has_previous:false,has_next:false } : {}) }
    } else if (publicRow(data)) safe = data
    if (safe === undefined) client.removeQueries({ queryKey: key, exact: true })
    else client.setQueryData(key, safe, { updatedAt: query.state.dataUpdatedAt })
  }
}
