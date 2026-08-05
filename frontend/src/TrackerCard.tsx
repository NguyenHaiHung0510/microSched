import { type FormEvent, type TouchEvent, useRef, useState } from 'react'
import { MoreHorizontal, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  amountToNumber,
  canSubmitAmount,
  digitsOnly,
  formatLastSeen,
  formatVnd,
  type Tracker,
} from '@/tracker-ui'

const LONG_PRESS_MS = 500
const CLICK_SUPPRESS_MS = 400

type TrackerCardProps = {
  tracker: Tracker
  locked: boolean
  pending: boolean
  /** input is the digit string for money/quantity trackers; undefined = event capture. */
  onCapture: (input?: string) => void
  onBackdate: () => void
}

export function TrackerCard({ tracker, locked, pending, onCapture, onBackdate }: TrackerCardProps) {
  const [inputOpen, setInputOpen] = useState(false)
  const [input, setInput] = useState('')
  const longPressTimer = useRef<number | null>(null)
  const longPressFired = useRef(false)
  const suppressClickUntil = useRef(0)

  function clearLongPress() {
    if (longPressTimer.current !== null) {
      window.clearTimeout(longPressTimer.current)
      longPressTimer.current = null
    }
  }

  function handleTouchStart() {
    longPressFired.current = false
    clearLongPress()
    longPressTimer.current = window.setTimeout(() => {
      longPressFired.current = true
      // iOS fires a synthetic click after touchend; ignoring it for a short window
      // is what keeps a long-press from ALSO running the one-tap capture (§5.3).
      suppressClickUntil.current = Date.now() + CLICK_SUPPRESS_MS
      onBackdate()
    }, LONG_PRESS_MS)
  }

  function handleTouchEnd(event: TouchEvent<HTMLButtonElement>) {
    clearLongPress()
    if (longPressFired.current) event.preventDefault()
  }

  function handleTouchMove() {
    clearLongPress()
    longPressFired.current = false
  }

  function handleClick() {
    if (Date.now() < suppressClickUntil.current) {
      suppressClickUntil.current = 0
      return
    }
    if (tracker.input_mode === 'event') {
      onCapture()
      return
    }
    setInputOpen(true)
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!canSubmitAmount(input) || locked || pending) return
    onCapture(digitsOnly(input))
    setInput('')
    setInputOpen(false)
  }

  const needsAmount = tracker.input_mode === 'money' || tracker.input_mode === 'quantity'
  const echoAmount = canSubmitAmount(input) ? amountToNumber(input) : null

  return (
    <Card
      data-tracker-id={tracker.id}
      className="relative gap-0 p-3 shadow-1 ring-0"
    >
      {inputOpen && needsAmount ? (
        <form className="space-y-2" onSubmit={submit}>
          <label className="block space-y-1 text-sm font-semibold">
            <span>{tracker.input_mode === 'money' ? 'Số tiền' : `Số lượng (${tracker.unit ?? 'đơn vị'})`}</span>
            <Input
              data-testid="tracker-amount-input"
              data-tracker-id={tracker.id}
              className="h-10 bg-card text-base"
              inputMode="numeric"
              autoFocus
              value={input}
              onChange={(event) => setInput(digitsOnly(event.target.value))}
            />
          </label>
          {echoAmount !== null ? (
            <p className="text-lg font-extrabold text-primary tabular-nums">
              = {formatVnd(echoAmount)}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button size="lg" type="submit" disabled={!canSubmitAmount(input) || locked || pending}>
              {pending ? 'Đang ghi…' : 'Ghi'}
            </Button>
            <Button
              size="lg"
              variant="ghost"
              type="button"
              onClick={() => {
                setInput('')
                setInputOpen(false)
              }}
            >
              Huỷ
            </Button>
          </div>
        </form>
      ) : (
        <>
          <Button
            data-testid="tracker-button"
            data-tracker-id={tracker.id}
            variant="secondary"
            className="h-auto min-h-11 min-w-0 flex-col items-start gap-0.5 px-3 py-2 text-left"
            disabled={locked}
            onTouchStart={handleTouchStart}
            onTouchEnd={handleTouchEnd}
            onTouchMove={handleTouchMove}
            onClick={handleClick}
          >
            <span className="max-w-full break-words text-sm font-bold">{tracker.name}</span>
            <span
              data-testid="tracker-last-seen"
              data-tracker-id={tracker.id}
              className="text-xs text-muted-foreground"
            >
              {formatLastSeen(tracker.last_entry_at)}
            </span>
          </Button>
          <Button
            data-testid="tracker-backdate"
            data-tracker-id={tracker.id}
            variant="ghost"
            size="icon-sm"
            className="absolute top-1.5 right-1.5"
            aria-label={`Ghi lùi giờ cho ${tracker.name}`}
            onClick={(event) => {
              event.stopPropagation()
              onBackdate()
            }}
          >
            <MoreHorizontal />
          </Button>
          {locked ? (
            <X className="pointer-events-none absolute top-1.5 left-1.5 size-3.5 text-muted-foreground" />
          ) : null}
        </>
      )}
    </Card>
  )
}
