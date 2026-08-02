import { toast } from 'sonner'

import { ApiError, apiRequest, TimeoutError, UnauthenticatedError } from '@/api'

type RefreshNotes = () => void

export function errorMessage(error: unknown): string {
  if (error instanceof UnauthenticatedError) return 'Phiên đã hết hạn. Tải lại để đăng nhập.'
  if (error instanceof TimeoutError) return error.message
  if (error instanceof ApiError) return error.message
  return 'Không kết nối được API.'
}

export async function restoreNote(noteId: string, refresh: RefreshNotes): Promise<void> {
  try {
    await apiRequest<{ id: string; status: 'restored' }>(`/api/notes/${noteId}/restore`, {
      method: 'POST',
    })
    refresh()
  } catch (error) {
    toast.error(errorMessage(error))
  }
}
