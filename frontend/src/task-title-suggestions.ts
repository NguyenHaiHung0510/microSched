/** Pure, bounded matching over the dedicated STANDARD-only title source. */
export type TitleHistory = { title: string; count: number }
type Candidate = TitleHistory & { kind: 'group' | 'title'; normalized: string }
export type TitleSuggestion = TitleHistory & { kind: 'group' | 'title'; tier: number }

export function normalizeTitle(value: string): string {
  return value.normalize('NFD').replace(/\p{M}/gu, '').replace(/[đĐ]/g, 'd')
    .toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim().replace(/\s+/g, ' ')
}

export function titleCandidates(history: readonly TitleHistory[]): Candidate[] {
  const candidates = new Map<string, Candidate>()
  const add = (title: string, count: number, kind: Candidate['kind']) => {
    const normalized = normalizeTitle(title)
    if (!normalized) return
    const key = `${kind}:${normalized}`
    const previous = candidates.get(key)
    if (previous) previous.count += count
    else candidates.set(key, { title, count, kind, normalized })
  }
  for (const { title: raw, count } of history.slice(0, 512)) {
    const title = raw.trim()
    if (!title || title.startsWith('enc:v1:') || !Number.isInteger(count) || count < 1 || count > 512) continue
    const group = title.match(/^(\[[^\]\r\n]+\])(?:\s|$)/u)?.[1]
    if (group) add(group, count, 'group')
    if (title !== group) add(title, count, 'title')
  }
  return [...candidates.values()]
}

/** Adjacent transpositions count once; short tokens never get fuzzy matches. */
function editDistance(a: string, b: string): number {
  const rows = Array.from({ length: a.length + 1 }, () => Array<number>(b.length + 1).fill(0))
  for (let i = 0; i <= a.length; i++) rows[i][0] = i
  for (let j = 0; j <= b.length; j++) rows[0][j] = j
  for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++) {
    rows[i][j] = Math.min(rows[i - 1][j] + 1, rows[i][j - 1] + 1,
      rows[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1))
    if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1])
      rows[i][j] = Math.min(rows[i][j], rows[i - 2][j - 2] + 1)
  }
  return rows[a.length][b.length]
}

function tokenDistance(query: string, target: string, fuzzy: boolean): number | null {
  if (target.startsWith(query)) return 0
  if (!fuzzy || query.length < 4 || query.length > 32 || target.length < 4) return null
  const allowance = query.length >= 7 ? 2 : 1
  // A typo can occur in the partially typed final word too.
  let best = allowance + 1
  for (let length = Math.max(4, query.length - allowance); length <= Math.min(target.length, query.length + allowance); length++)
    best = Math.min(best, editDistance(query, target.slice(0, length)))
  return best <= allowance ? best : null
}

/** One candidate token per query token; no accidental matching of repeated words. */
function matchTokens(query: string[], target: string[], fuzzy: boolean): number | null {
  if (query.length > target.length) return null
  const edges = query.map(token => target.map(word => tokenDistance(token, word, fuzzy)))
  const owners = Array<number>(target.length).fill(-1)
  function assign(queryIndex: number, seen: Set<number>): boolean {
    const choices = edges[queryIndex].map((cost, index) => ({ cost, index }))
      .filter((edge): edge is { cost: number; index: number } => edge.cost !== null)
      .sort((a, b) => a.cost - b.cost)
    for (const { index } of choices) {
      if (seen.has(index)) continue
      seen.add(index)
      if (owners[index] === -1 || assign(owners[index], seen)) {
        owners[index] = queryIndex
        return true
      }
    }
    return false
  }
  const order = query.map((_, i) => i).sort((a, b) => query[b].length - query[a].length)
  if (!order.every(i => assign(i, new Set()))) return null
  return owners.reduce((sum, owner, i) => sum + (owner < 0 ? 0 : edges[owner][i]!), 0)
}

export function rankTitleSuggestions(value: string, candidates: readonly Candidate[]): TitleSuggestion[] {
  const query = normalizeTitle(value)
  // Keep ordinary free-form submission for weak/empty or implausibly long input.
  if (query.replace(/\s/g, '').length < 2 || query.length > 160) return []
  const words = query.split(' ')
  if (words.length > 12) return []
  return candidates.flatMap(candidate => {
    const target = candidate.normalized
    let tier: number
    let distance = 0
    if (query === target) tier = 0
    else if (target.startsWith(query)) tier = 1
    else if (matchTokens(words, target.split(' '), false) !== null) tier = 2
    else {
      const fuzzy = matchTokens(words, target.split(' '), true)
      if (fuzzy === null || fuzzy === 0 || fuzzy > 2) return []
      tier = 3
      distance = fuzzy
    }
    return [{ ...candidate, tier, distance }]
  }).sort((a, b) => a.tier - b.tier || a.distance - b.distance || Number(a.kind === 'title') - Number(b.kind === 'title') ||
    b.count - a.count || a.title.localeCompare(b.title, 'vi'))
    .slice(0, 6)
}
