import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { Bell, CheckCircle2, Home } from 'lucide-react'
import { toast } from 'sonner'

import { ApiError, TimeoutError, apiRequest } from '@/api'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { navigate, queryParams, useLocation } from '@/lib/route'
import { uuidv7 } from '@/lib/uuidv7'
import { privateError, unlockPrivate, type PrivateSessionState } from '@/private-gate'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'

interface ConfirmResponse {
  confirmed_entry_id: string
  created: boolean
}

/** Backend shape: backend/app/domain/reminder.py — 403 với detail.code. */
function isPrivateUnlockRequired(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 403) return false
  const detail = (error.body as { detail?: { code?: unknown } } | undefined)?.detail
  return (
    typeof detail === 'object' &&
    detail !== null &&
    (detail as { code?: unknown }).code === 'PRIVATE_UNLOCK_REQUIRED'
  )
}

/** fetch() hỏng mạng (TypeError) và hết giờ của apiRequest (TimeoutError). */
function isNetworkFailure(error: unknown): boolean {
  return error instanceof TimeoutError || error instanceof TypeError
}

export function ReminderConfirmScreen() {
  const location = useLocation()
  const queryClient = useQueryClient()
  // F9: entryId/occurredAt đóng băng ở state — retry sau khi mở khoá gửi NGUYÊN body.
  const [entryId] = useState(() => uuidv7())
  const [occurredAt] = useState(() => new Date().toISOString())
  const [confirmed, setConfirmed] = useState(false)
  const [unlockOpen, setUnlockOpen] = useState(false)
  const [pin, setPin] = useState('')
  const [unlockError, setUnlockError] = useState<string | null>(null)

  const dispatchId = queryParams(location).get('dispatch')

  // Cùng key/shape với session query của App (endpoint /api/me — không có
  // /api/private/session). Endpoint confirm đọc `private_until` phía server nên
  // unlock xong chỉ cần invalidate key này rồi retry.
  const { data: session } = useQuery<PrivateSessionState>({
    queryKey: ['session'],
    queryFn: () => apiRequest<PrivateSessionState>('/api/me'),
    ...NO_POLLING_QUERY_OPTIONS,
  })

  const confirmMutation = useMutation({
    mutationFn: async () => {
      if (!dispatchId) {
        throw new Error('Thiếu dispatch ID')
      }
      return apiRequest<ConfirmResponse>(
        `/api/reminder-dispatch/${dispatchId}/confirm`,
        {
          method: 'POST',
          body: JSON.stringify({
            entry_id: entryId,
            occurred_at: occurredAt,
          }),
        }
      )
    },
    onSuccess: (data) => {
      if (data.created) {
        toast.success('Đã ghi nhận uống thuốc', { duration: 10000 })
      } else {
        toast.info('Lần uống này đã được ghi từ trước', { duration: 10000 })
      }
      navigate('/')
    },
    onError: (error) => {
      // F9: khoản mục riêng tư KHÔNG được làm mất nhắc — mở flow mở khoá,
      // retry sau khi unlock thành công.
      if (isPrivateUnlockRequired(error)) {
        setUnlockOpen(true)
        return
      }
      // F9: mạng hỏng không phải phán quyết — giữ màn hình, toast hướng dẫn.
      if (isNetworkFailure(error)) {
        toast.error('Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.', {
          duration: 10000,
        })
        return
      }
      toast.error(error.message || 'Không thể xác nhận lời nhắc', { duration: 10000 })
      navigate('/')
    },
  })

  const unlockMutation = useMutation({
    mutationFn: unlockPrivate,
    onSuccess: () => {
      setPin('')
      setUnlockError(null)
      setUnlockOpen(false)
      void queryClient.invalidateQueries({ queryKey: ['session'] })
      // Retry ĐÚNG dispatch cũ với ĐÚNG body cũ (entryId/occurredAt đã đóng băng).
      confirmMutation.mutate()
    },
    onError: (error) => {
      const details = privateError(error)
      setUnlockError(details?.message ?? 'Không thể mở khoá riêng tư. Thử lại sau.')
      void queryClient.invalidateQueries({ queryKey: ['session'] })
    },
  })

  const submitUnlock = (event: FormEvent) => {
    event.preventDefault()
    setUnlockError(null)
    unlockMutation.mutate(pin)
  }

  useEffect(() => {
    if (!dispatchId) {
      toast.error('Liên kết nhắc nhở không hợp lệ', { duration: 10000 })
      navigate('/')
    }
  }, [dispatchId])

  // JC4: nếu khoản mục đang riêng tư, hướng dẫn trực quan ngay từ đầu.
  useEffect(() => {
    if (session && !session.private_until) {
      toast.info('Khoản mục riêng tư: Hãy mở Chế độ Riêng tư (mở PIN) để xem chi tiết.', {
        duration: 12000,
      })
    }
  }, [session])

  return (
    <Card className="mx-auto max-w-lg gap-4 rounded-lg bg-card p-6 shadow-2 ring-0" role="status">
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary">
          <Bell className="size-5" />
        </div>
        <div>
          <h1 className="text-xl font-extrabold tracking-tight text-primary">microSched</h1>
          <p className="text-sm text-muted-foreground">Xác nhận lời nhắc uống thuốc / theo dõi</p>
        </div>
      </div>

      <div className="space-y-3 rounded-lg border border-border bg-muted/40 p-4">
        <p className="text-sm font-semibold">
          Bạn có một thông báo nhắc nhở đã đến giờ thực hiện.
        </p>
        <label className="flex min-h-11 items-center gap-3 text-sm font-semibold cursor-pointer">
          <Checkbox
            data-testid="reminder-confirm-checkbox"
            className="size-5 rounded-md"
            checked={confirmed}
            onCheckedChange={(checked) => setConfirmed(checked === true)}
          />
          <span>Đánh dấu đã hoàn thành lần nhắc này</span>
        </label>
      </div>

      <div className="flex flex-wrap gap-2 pt-2">
        <Button
          data-testid="reminder-confirm-submit"
          size="lg"
          className="min-h-11"
          disabled={!confirmed || confirmMutation.isPending}
          onClick={() => confirmMutation.mutate()}
        >
          <CheckCircle2 data-icon="inline-start" className="size-4" />
          {confirmMutation.isPending ? 'Đang xác nhận…' : 'Xác nhận đã uống'}
        </Button>
        <Button
          size="lg"
          variant="outline"
          className="min-h-11"
          onClick={() => navigate('/')}
        >
          <Home data-icon="inline-start" className="size-4" />
          Về trang chủ
        </Button>
        {confirmMutation.isError ? (
          <Button
            data-testid="reminder-confirm-retry"
            size="lg"
            variant="secondary"
            className="min-h-11"
            onClick={() => confirmMutation.mutate()}
          >
            Thử lại
          </Button>
        ) : null}
      </div>

      <Dialog open={unlockOpen} onOpenChange={setUnlockOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Mở dữ liệu riêng tư</DialogTitle>
            <DialogDescription>
              Khoản mục nhắc nhở đang riêng tư — mở khoá để xác nhận lần uống này.
            </DialogDescription>
          </DialogHeader>
          <form className="space-y-4" onSubmit={submitUnlock}>
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="private-pin">
                PIN 6 chữ số
              </label>
              <Input
                id="private-pin"
                data-testid="private-pin-input"
                type="password"
                name="private-pin"
                inputMode="numeric"
                maxLength={6}
                autoComplete="current-password"
                value={pin}
                onChange={(event) => setPin(event.target.value)}
                autoFocus
              />
            </div>
            {unlockError ? <p className="text-sm text-bad">{unlockError}</p> : null}
            <DialogFooter>
              <Button
                type="submit"
                size="lg"
                data-testid="private-unlock-submit"
                disabled={!/^[0-9]{6}$/.test(pin) || unlockMutation.isPending}
              >
                Mở khoá
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
