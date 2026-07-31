/** Shared same-origin API primitives for authenticated screens. */

export class UnauthenticatedError extends Error {}

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, message: string, body?: unknown) {
    super(message)
    this.status = status
    this.body = body
  }
}

/** Mạng treo là một kết cục riêng, không phải một lỗi HTTP — nó cần lời riêng. */
export class TimeoutError extends Error {}

/* Máy chủ chạy scale-to-zero nên lần gọi đầu sau khi máy ngủ phải trả tiền đánh
   thức (đo được khoảng 8 giây). 20 giây là gấp đôi con số đó cộng biên: đủ rộng
   để một lần đánh thức bình thường KHÔNG bị cắt oan, đủ hẹp để người dùng không
   ngồi nhìn một nút đứng im tới vô hạn. */
const REQUEST_TIMEOUT_MS = 20_000

/* Hạn 20 giây là hạn của MỌI request, kể cả khi người gọi tự mang signal của mình.
   Viết `init.signal ?? timeout` thì signal của người gọi THAY THẾ hạn giờ — ai đó ở
   009–012 truyền vào một signal chỉ để huỷ khi component unmount là vô tình gỡ mất
   hạn giờ cho đúng request đó, và không có gì báo. Ghép hai signal, đừng chọn một.

   Ghép tay chứ không dùng `AbortSignal.any`: hàm đó cần iOS 17.4, còn
   `AbortSignal.timeout` chỉ cần iOS 16. Thiết bị chính của chủ là iPhone nên đừng
   nâng sàn thiết bị chỉ để bớt bốn dòng code. */
function requestSignal(callerSignal: AbortSignal | null | undefined): AbortSignal {
  const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS)
  if (!callerSignal) return timeout

  const controller = new AbortController()
  for (const source of [callerSignal, timeout]) {
    if (source.aborted) {
      controller.abort(source.reason)
      break
    }
    // `reason` được chuyển tiếp nguyên vẹn: nhờ đó hạn giờ vẫn tới `catch` bên dưới
    // dưới dạng DOMException tên `TimeoutError`, không bị hoá thành `AbortError`.
    source.addEventListener('abort', () => controller.abort(source.reason), {
      once: true,
    })
  }
  return controller.signal
}

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
      signal: requestSignal(init?.signal),
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

  let body: unknown
  if (response.status !== 204) {
    try {
      body = await response.json()
    } catch {
      // A proxy may return a non-JSON error; status still carries the verdict.
    }
  }

  const detail =
    body && typeof body === 'object' && 'detail' in body
      ? (body as { detail?: unknown }).detail
      : undefined

  // Private PIN mismatch deliberately uses 401 too, with a different envelope.
  // Only the shared auth guard means "the login session is gone".
  if (
    response.status === 401 &&
    (body === undefined || detail === 'Not authenticated')
  ) {
    throw new UnauthenticatedError('No active session')
  }

  if (!response.ok) {
    const message =
      typeof detail === 'string'
        ? detail
        : `API request failed with status ${response.status}`
    throw new ApiError(response.status, message, body)
  }

  if (response.status === 204) return undefined as T
  return body as T
}
