import { ApiError, TimeoutError, UnauthenticatedError } from '@/api'

export function errorMessage(error: unknown): string {
  if (error instanceof UnauthenticatedError) return 'Phiên đã hết hạn. Tải lại để đăng nhập.'
  if (error instanceof TimeoutError) return error.message
  if (error instanceof ApiError) return error.message
  return 'Không kết nối được API.'
}
