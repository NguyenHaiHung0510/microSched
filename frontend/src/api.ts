/** Shared same-origin API primitives for authenticated screens. */

export class UnauthenticatedError extends Error {}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** Mạng treo là một kết cục riêng, không phải một lỗi HTTP — nó cần lời riêng. */
export class TimeoutError extends Error {}

/* Máy chủ chạy scale-to-zero nên lần gọi đầu sau khi máy ngủ phải trả tiền đánh
   thức (đo được khoảng 8 giây). 20 giây là gấp đôi con số đó cộng biên: đủ rộng
   để một lần đánh thức bình thường KHÔNG bị cắt oan, đủ hẹp để người dùng không
   ngồi nhìn một nút đứng im tới vô hạn. */
const REQUEST_TIMEOUT_MS = 20_000

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      credentials: 'same-origin',
      // Không có dòng này thì `fetch` KHÔNG bao giờ tự bỏ cuộc: request treo ⇒
      // promise không bao giờ settle ⇒ mutation kẹt `isPending` vĩnh viễn ⇒ nút
      // đứng ở "Đang thêm…" mà không lỗi, không retry, không đường thoát ngoài
      // tải lại trang. Đã gặp thật khi QA 2026-07-25.
      signal: init?.signal ?? AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      headers: {
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new TimeoutError('Máy chủ không trả lời. Kiểm tra mạng rồi thử lại.')
    }
    throw error
  }

  if (response.status === 401) {
    throw new UnauthenticatedError('No active session')
  }

  if (!response.ok) {
    let message = `API request failed with status ${response.status}`
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) message = body.detail
    } catch {
      // The status remains the useful error when a proxy returns a non-JSON body.
    }
    throw new ApiError(response.status, message)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
