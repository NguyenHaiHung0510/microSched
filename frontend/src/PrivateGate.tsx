import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { KeyRound, Lock, LockOpen } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  changePrivatePin,
  countdownLabel,
  expirePrivateSession,
  lockPrivate,
  privateError,
  remainingSeconds,
  unlockPrivate,
  type PrivateSessionState,
} from '@/private-gate'
import { taskInvalidationKey } from '@/task-ui'

type Props = {
  session: PrivateSessionState
  onVisibilityChange?: () => void
}

function messageFor(error: unknown): {
  text: string
  retryAfterSeconds?: number
} {
  const details = privateError(error)
  if (!details) return { text: 'Không thể cập nhật cổng riêng tư. Thử lại sau.' }
  if (details.status === 401 && details.remaining !== undefined) {
    return {
      text: `Sai PIN. Còn ${details.remaining} lần trước khi khoá tạm.`,
    }
  }
  if (details.status === 429 && details.retryAfterSeconds !== undefined) {
    return {
      text: `Đang khoá tạm · còn ${countdownLabel(details.retryAfterSeconds)}.`,
      retryAfterSeconds: details.retryAfterSeconds,
    }
  }
  return { text: details.message }
}

function isSixAsciiDigits(value: string): boolean {
  return /^[0-9]{6}$/.test(value)
}

export function PrivateGate({ session, onVisibilityChange }: Props) {
  const queryClient = useQueryClient()
  const [privateOverride, setPrivateOverride] = useState<string | null>()
  const [lockedOverride, setLockedOverride] = useState<string | null>()
  const [clock, setClock] = useState(0)
  const [unlockOpen, setUnlockOpen] = useState(false)
  const [changeOpen, setChangeOpen] = useState(false)
  const [pin, setPin] = useState('')
  const [currentPin, setCurrentPin] = useState('')
  const [newPin, setNewPin] = useState('')
  const [confirmPin, setConfirmPin] = useState('')
  const [errorText, setErrorText] = useState<string | null>(null)

  const privateUntil = privateOverride === undefined ? session.private_until : privateOverride
  const lockedUntil =
    lockedOverride === undefined ? session.private_locked_until : lockedOverride

  const invalidateStatus = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['session'] })
  }, [queryClient])

  const expireIfNeeded = useCallback(() => {
    if (!expirePrivateSession(queryClient, privateUntil)) return false
    setPrivateOverride(null)
    invalidateStatus()
    void queryClient.invalidateQueries({ queryKey: taskInvalidationKey })
    void queryClient.invalidateQueries({ queryKey: ['calendar'] })
    onVisibilityChange?.()
    return true
  }, [invalidateStatus, onVisibilityChange, privateUntil, queryClient])

  useEffect(() => {
    if (!privateUntil) return
    let timeout = 0
    const schedule = () => {
      const delay = Math.max(0, Date.parse(privateUntil) - Date.now())
      timeout = window.setTimeout(() => {
        // A callback can fire a fraction early. Reschedule instead of leaving a
        // future gate with no timer after that one premature callback.
        if (!expireIfNeeded()) schedule()
      }, delay)
    }
    schedule()
    return () => window.clearTimeout(timeout)
  }, [expireIfNeeded, privateUntil])

  useEffect(() => {
    const checkVisibleDeadline = () => {
      if (document.visibilityState === 'visible') expireIfNeeded()
    }
    const checkFocusedDeadline = () => expireIfNeeded()
    document.addEventListener('visibilitychange', checkVisibleDeadline)
    window.addEventListener('focus', checkFocusedDeadline)
    return () => {
      document.removeEventListener('visibilitychange', checkVisibleDeadline)
      window.removeEventListener('focus', checkFocusedDeadline)
    }
  }, [expireIfNeeded])

  useEffect(() => {
    if (!privateUntil && !lockedUntil) return
    // Display clock only. The hard expiry is the exact setTimeout plus the
    // focus/visibility checks above; this tick never grants or revokes access.
    let timeout = 0
    const tick = () => {
      setClock(Date.now())
      timeout = window.setTimeout(tick, 1000)
    }
    timeout = window.setTimeout(tick, 0)
    return () => window.clearTimeout(timeout)
  }, [lockedUntil, privateUntil])

  const reportError = useCallback((error: unknown) => {
    const result = messageFor(error)
    setErrorText(result.text)
    // The first failed attempt may lazily seed the bootstrap row, and a 429
    // persists a global deadline. Refresh the one shared session query so the
    // permanent bootstrap warning and every other consumer see that state too.
    invalidateStatus()
    if (result.retryAfterSeconds !== undefined) {
      setLockedOverride(
        new Date(Date.now() + result.retryAfterSeconds * 1000).toISOString(),
      )
    }
  }, [invalidateStatus])

  const unlock = useMutation({
    mutationFn: unlockPrivate,
    onSuccess: (result) => {
      setPrivateOverride(result.private_until)
      setLockedOverride(null)
      setPin('')
      setErrorText(null)
      setUnlockOpen(false)
      invalidateStatus()
      void queryClient.invalidateQueries({ queryKey: taskInvalidationKey })
      void queryClient.invalidateQueries({ queryKey: ['calendar'] })
      onVisibilityChange?.()
    },
    onError: reportError,
  })

  const lock = useMutation({
    mutationFn: lockPrivate,
    onSuccess: () => {
      // R6 order is load-bearing: erase private responses before any refetch can
      // leave the previous result rendered while the network request is pending.
      queryClient.removeQueries({ queryKey: taskInvalidationKey })
      queryClient.removeQueries({ queryKey: ['calendar'] })
      setPrivateOverride(null)
      setErrorText(null)
      invalidateStatus()
      void queryClient.invalidateQueries({ queryKey: taskInvalidationKey })
      onVisibilityChange?.()
    },
    onError: reportError,
  })

  const changePin = useMutation({
    mutationFn: () => changePrivatePin(session.pin_is_set ? currentPin : null, newPin),
    onSuccess: () => {
      setCurrentPin('')
      setNewPin('')
      setConfirmPin('')
      setErrorText(null)
      setChangeOpen(false)
      invalidateStatus()
    },
    onError: reportError,
  })

  const privateSeconds = remainingSeconds(privateUntil, clock)
  const lockedSeconds = remainingSeconds(lockedUntil, clock)
  const isOpen = privateSeconds > 0
  const isThrottled = lockedSeconds > 0

  const submitUnlock = (event: FormEvent) => {
    event.preventDefault()
    setErrorText(null)
    unlock.mutate(pin)
  }

  const submitChange = (event: FormEvent) => {
    event.preventDefault()
    if (!isSixAsciiDigits(newPin)) {
      setErrorText('PIN phải đúng 6 chữ số')
      return
    }
    if (newPin !== confirmPin) {
      setErrorText('PIN mới nhập lại chưa khớp')
      return
    }
    setErrorText(null)
    changePin.mutate()
  }

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <Badge
        data-testid="private-badge"
        variant={isOpen ? 'default' : isThrottled ? 'destructive' : 'outline'}
      >
        {isThrottled ? (
          <>
            <Lock data-icon="inline-start" /> Khoá tạm · còn {countdownLabel(lockedSeconds)}
          </>
        ) : isOpen ? (
          <>
            <LockOpen data-icon="inline-start" /> Riêng tư · còn{' '}
            {Math.max(1, Math.ceil(privateSeconds / 60))} phút
          </>
        ) : (
          <>
            <Lock data-icon="inline-start" /> Riêng tư · đang khoá
          </>
        )}
      </Badge>

      {isOpen ? (
        <Button
          type="button"
          variant="softRose"
          size="sm"
          className="min-h-11"
          data-testid="private-lock-now"
          disabled={lock.isPending}
          onClick={() => lock.mutate()}
        >
          <Lock data-icon="inline-start" /> Khoá lại ngay
        </Button>
      ) : (
        <Button
          type="button"
          variant="softRose"
          size="sm"
          className="min-h-11"
          data-testid="private-unlock-open"
          disabled={isThrottled}
          onClick={() => setUnlockOpen(true)}
        >
          <LockOpen data-icon="inline-start" /> Mở khoá
        </Button>
      )}

      <Button
        type="button"
        variant="ghost"
        size="icon-lg"
        className="size-11"
        data-testid="private-pin-change-open"
        aria-label="Đổi PIN riêng tư"
        onClick={() => setChangeOpen(true)}
      >
        <KeyRound />
      </Button>

      {session.pin_is_bootstrap ? (
        <p className="basis-full text-right text-xs text-bad">
          PIN còn là mặc định — hãy đổi
        </p>
      ) : null}
      {errorText ? (
        <p
          className="basis-full text-right text-xs text-bad"
          data-testid="private-error"
          role="alert"
        >
          {errorText}
        </p>
      ) : null}

      <Dialog open={unlockOpen} onOpenChange={setUnlockOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Mở dữ liệu riêng tư</DialogTitle>
            <DialogDescription>
              Phiên mở trong 36 phút và không tự gia hạn khi bạn tiếp tục dùng app.
            </DialogDescription>
          </DialogHeader>
          <form className="space-y-4" onSubmit={submitUnlock}>
            <Input
              className="sr-only"
              value={session.email}
              name="username"
              autoComplete="username"
              readOnly
              aria-label="Tài khoản"
            />
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
            {errorText ? <p className="text-sm text-bad">{errorText}</p> : null}
            <DialogFooter>
              <Button
                type="submit"
                size="lg"
                data-testid="private-unlock-submit"
                disabled={!isSixAsciiDigits(pin) || unlock.isPending || isThrottled}
              >
                Mở khoá
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={changeOpen} onOpenChange={setChangeOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{session.pin_is_set ? 'Đổi PIN' : 'Đặt PIN'}</DialogTitle>
            <DialogDescription>
              PIN chỉ mở cổng hiển thị; khoá mã hoá dữ liệu vẫn độc lập.
            </DialogDescription>
          </DialogHeader>
          <form className="space-y-4" onSubmit={submitChange}>
            <Input
              className="sr-only"
              value={session.email}
              name="username"
              autoComplete="username"
              readOnly
              aria-label="Tài khoản"
            />
            {session.pin_is_set ? (
              <div className="space-y-1.5">
                <label className="text-sm font-medium" htmlFor="current-private-pin">
                  PIN hiện tại
                </label>
                <Input
                  id="current-private-pin"
                  type="password"
                  name="current-private-pin"
                  inputMode="numeric"
                  maxLength={6}
                  autoComplete="current-password"
                  value={currentPin}
                  onChange={(event) => setCurrentPin(event.target.value)}
                />
              </div>
            ) : null}
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="new-private-pin">
                PIN mới
              </label>
              <Input
                id="new-private-pin"
                type="password"
                name="new-private-pin"
                inputMode="numeric"
                maxLength={6}
                autoComplete="new-password"
                value={newPin}
                onChange={(event) => setNewPin(event.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="confirm-private-pin">
                Nhập lại PIN mới
              </label>
              <Input
                id="confirm-private-pin"
                type="password"
                name="confirm-private-pin"
                inputMode="numeric"
                maxLength={6}
                autoComplete="new-password"
                value={confirmPin}
                onChange={(event) => setConfirmPin(event.target.value)}
              />
            </div>
            {errorText ? <p className="text-sm text-bad">{errorText}</p> : null}
            <DialogFooter>
              <Button
                type="submit"
                size="lg"
                disabled={
                  changePin.isPending ||
                  !isSixAsciiDigits(newPin) ||
                  newPin !== confirmPin ||
                  (session.pin_is_set && !isSixAsciiDigits(currentPin))
                }
              >
                Lưu PIN
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
