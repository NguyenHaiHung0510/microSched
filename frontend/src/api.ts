/** Shared same-origin API primitives for authenticated screens. */

export class UnauthenticatedError extends Error {}

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

/** Mạng treo là một kết cục riêng, không phải một lỗi HTTP — nó cần lời riêng. */
export class TimeoutError extends Error {}

/* Máy chủ chạy scale-to-zero nên lần gọi đầu sau khi máy ngủ phải trả tiền đánh
   thức (đo được khoảng 8 giây). 20 giây là gấp đôi con số đó cộng biên: đủ rộng
   để một lần đánh thức bình thường KHÔNG bị cắt oan, đủ hẹp để người dùng không
   ngồi nhìn một nút đứng im tới vô hạn. */
const REQUEST_TIMEOUT_MS = 20_000
type ApiRequestInit = RequestInit & { timeoutMs?: number }

/* Hạn 20 giây là hạn của MỌI request, kể cả khi người gọi tự mang signal của mình.
   Viết `init.signal ?? timeout` thì signal của người gọi THAY THẾ hạn giờ — ai đó ở
   009–012 truyền vào một signal chỉ để huỷ khi component unmount là vô tình gỡ mất
   hạn giờ cho đúng request đó, và không có gì báo. Ghép hai signal, đừng chọn một.

   Ghép tay chứ không dùng `AbortSignal.any`: hàm đó cần iOS 17.4, còn
   `AbortSignal.timeout` chỉ cần iOS 16. Thiết bị chính của chủ là iPhone nên đừng
   nâng sàn thiết bị chỉ để bớt bốn dòng code. */
function requestSignal(
  callerSignal: AbortSignal | null | undefined,
  timeoutMs: number,
): AbortSignal {
  const timeout = AbortSignal.timeout(timeoutMs)
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

export async function apiRequest<T>(path: string, init?: ApiRequestInit): Promise<T> {
  let response: Response
  const { timeoutMs = REQUEST_TIMEOUT_MS, ...requestInit } = init ?? {}
  try {
    response = await fetch(path, {
      ...requestInit,
      credentials: 'same-origin',
      // Không có dòng này thì `fetch` KHÔNG bao giờ tự bỏ cuộc: request treo ⇒
      // promise không bao giờ settle ⇒ mutation kẹt `isPending` vĩnh viễn ⇒ nút
      // đứng ở "Đang thêm…" mà không lỗi, không retry, không đường thoát ngoài
      // tải lại trang. Đã gặp thật khi QA 2026-07-25.
      signal: requestSignal(requestInit.signal, timeoutMs),
      headers: {
        ...(requestInit.body ? { 'Content-Type': 'application/json' } : {}),
        ...requestInit.headers,
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
    let detail: unknown
    try {
      const body = (await response.json()) as { detail?: unknown }
      detail = body.detail
      if (typeof body.detail === 'string' && body.detail) message = body.detail
    } catch {
      // The status remains the useful error when a proxy returns a non-JSON body.
    }
    throw new ApiError(response.status, message, detail)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
