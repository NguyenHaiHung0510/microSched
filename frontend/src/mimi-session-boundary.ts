import type { QueryClient } from '@tanstack/react-query'
import { selectMimiConversation } from './mimi-selection'

const epochs = new WeakMap<QueryClient, number>()
export const mimiSessionEpoch = (client: QueryClient) => epochs.get(client) ?? 0
export const isMimiSessionCurrent = (client: QueryClient, epoch: number) => mimiSessionEpoch(client) === epoch

/** Auth loss/logout/principal change wins over STANDARD draft retention.
 * Private PIN lock is deliberately a separate boundary. */
export function purgeMimiSession(client: QueryClient) {
  epochs.set(client, mimiSessionEpoch(client) + 1)
  const predicate = (query: { queryKey: readonly unknown[] }) => ['mimi', 'mimi-feedback-draft', 'mimi-decision-fences'].includes(String(query.queryKey[0]))
  void client.cancelQueries({ predicate }, { revert: false })
  client.removeQueries({ predicate })
  // Settled/pending mutation variables may also contain feedback/chat prose.
  // Remove only explicitly Mimi-owned receipts; this does not cancel/replay
  // the HTTP mutation. Epoch guards still fence any later callbacks.
  const mutations = client.getMutationCache()
  for (const mutation of mutations.getAll()) if (mutation.options.mutationKey?.[0] === 'mimi') mutations.remove(mutation)
  if (typeof window !== 'undefined') selectMimiConversation(null)
  // Existing opaque decision bindings contain no prose. Retain the original
  // UNKNOWN key for explicit same-owner recovery; every API still checks auth
  // and conversation ownership. Purging it would silently forget an unknown write.
}
