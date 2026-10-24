import type { Command, Fields } from './protocol'

export function fundingReference(row: Pick<Command, 'kind'|'payload'>): string | null {
  if (!row.kind.startsWith('entry.')) return null
  try { const value = JSON.parse(row.payload).funding_entry_id; return typeof value === 'string' ? value : null } catch { return null }
}
export function needsFunding(row: Pick<Command, 'kind'|'payload'>): boolean {
  if (!row.kind.startsWith('entry.')) return false
  try { return 'funding_entry_id' in JSON.parse(row.payload) } catch { return false }
}
/** An Entry can be public while its optional income source is private. */
export function withoutFunding(row: Fields): Fields {
  const clean = {...row}; delete clean.funding; delete clean.funding_entry_id
  return clean
}
