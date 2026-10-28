import Dexie, { type Table } from 'dexie'
import type { Command } from './protocol'

class Outbox extends Dexie {
  rows!: Table<Command, number>
  constructor() {
    super('microsched-outbox-v1')
    this.version(1).stores({rows:'++operation_id,&id,principal,aggregate,state'})
  }
}
export const db = new Outbox()
export const byOrder = (a: Command,b: Command) => (a.operation_id ?? 0) - (b.operation_id ?? 0)

/** Called only inside the caller's write transaction. */
export async function removeAndSplice(removed: Command[]): Promise<void> {
  const all = await db.rows.toArray()
  const ids = new Set(removed.map(r => r.id))
  const old = new Map(all.map(r => [r.id,r]))
  for (const row of all) {
    if (ids.has(row.id)) continue
    let predecessor = row.predecessor
    while (predecessor && ids.has(predecessor)) predecessor = old.get(predecessor)?.predecessor ?? null
    const dependency = row.dependency && ids.has(row.dependency) ? null : row.dependency
    if (predecessor !== row.predecessor || dependency !== row.dependency)
      await db.rows.update(row.operation_id!, {predecessor,dependency})
  }
  await db.rows.bulkDelete(removed.map(r => r.operation_id!))
}
export function semanticTree(root: Command, all: Command[]): Command[] {
  const ids = new Set([root.id])
  let changed = true
  while (changed) {
    changed = false
    for (const r of all) if (r.dependency && ids.has(r.dependency) && !ids.has(r.id)) { ids.add(r.id); changed = true }
  }
  return all.filter(r => ids.has(r.id))
}
