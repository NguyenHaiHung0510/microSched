import { toast } from 'sonner'

import { ApiError, TimeoutError, UnauthenticatedError } from '@/api'
import { adapterFor } from '@/lib/outbox-adapters'
import { queuedRequest } from '@/lib/queued-mutation'
import { restoreCancelledOutbox, type Json, type OutboxRow } from '@/lib/outbox-db'
import type { QueryClient } from '@tanstack/react-query'

type DeleteReceipt = { cancelledRows: OutboxRow[] }

function snapshotJson(value: Record<string, unknown>): Json {
  const serialized = JSON.stringify(value)
  if (serialized === undefined) throw new TypeError('Note snapshot is not JSON serializable')
  return JSON.parse(serialized) as Json
}

export function errorMessage(error: unknown): string {
  if (error instanceof UnauthenticatedError) return 'Phiên đã hết hạn. Tải lại để đăng nhập.'
  if (error instanceof TimeoutError) return error.message
  if (error instanceof ApiError) return error.message
  return 'Không kết nối được API.'
}

export async function restoreNote(client: QueryClient, note: Record<string, unknown>, receipt: DeleteReceipt | null): Promise<void> {
  try {
    if (receipt?.cancelledRows.length) {
      const restored = await restoreCancelledOutbox(receipt.cancelledRows)
      for (const row of restored) await adapterFor(row.operation_kind).optimisticApply(client, row)
      window.dispatchEvent(new Event('microsched:outbox-flush-requested'))
      return
    }
    await queuedRequest<unknown>(client, 'note.restore', {
      path: `/api/notes/${String(note.id)}/restore`,
      entityId: String(note.id),
      requiresPrivate: note.is_private === true,
      optimisticEntity: snapshotJson(note),
    })
  } catch (error) {
    toast.error(errorMessage(error))
  }
}
