import { X } from 'lucide-react'
import { useId, useRef, useState, useEffect } from 'react'
import type { MimiCapabilities, MimiConversation } from '@/mimi-api'
import { Button } from '@/components/ui/button'
import { Popover, PopoverClose, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { lastMeasuredInput, formatMetric as format } from '@/mimi-context-metrics'
import { MimiConversationMetrics } from '@/MimiConversationMetrics'

export function MimiContextComposition({ conversation }: { conversation: MimiConversation; capabilities?: MimiCapabilities }) {
  const [open, setOpen] = useState(false)
  const pinned = useRef(false)
  const restoring = useRef(false)
  const pointerFocus = useRef(false)
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const titleId = useId()
  const actual = lastMeasuredInput(conversation)
  const compact = 400000
  const percent = actual == null ? 0 : Math.min(actual / compact * 100, 100)
  function clearClose() { if (closeTimer.current) { clearTimeout(closeTimer.current); closeTimer.current = null } }
  function leave() { clearClose(); if (!pinned.current) closeTimer.current = setTimeout(() => setOpen(false), 240) }
  useEffect(() => () => { if (closeTimer.current) clearTimeout(closeTimer.current) }, [])
  return <Popover open={open} onOpenChange={next => { setOpen(next); if (!next) { pinned.current = false; restoring.current = true } }}>
    <PopoverTrigger asChild><Button type="button" variant="ghost" className="mimi-context-meter min-h-11 shrink-0 gap-2" data-testid="mimi-run-context-inspector"
      aria-label={`Context đã đo: ${actual == null ? 'usage chưa xác định' : format(actual) + ' trên ' + format(compact) + ' tokens, call gần nhất'}`}
      onPointerDown={() => { pointerFocus.current = true }} onPointerUp={() => { pointerFocus.current = false }}
      onPointerEnter={event => { if (event.pointerType === 'mouse') { clearClose(); setOpen(true) } }} onPointerLeave={leave}
      onFocus={() => { if (restoring.current) { restoring.current = false; return } if (!pointerFocus.current) setOpen(true) }}
      onClick={event => { event.preventDefault(); clearClose(); pinned.current = true; setOpen(true) }}>
      <span className="mimi-context-ring" style={{ '--context-percent': `${percent}%` } as React.CSSProperties} aria-hidden="true" />
      <span className="hidden text-xs sm:inline">{actual == null ? '— / 400k' : `${format(actual)} / 400k`}</span>

    </Button></PopoverTrigger>
    <PopoverContent className="w-[min(26rem,calc(100vw-2rem))] max-h-[75dvh] overflow-y-auto" align="end" aria-labelledby={titleId} onOpenAutoFocus={event => event.preventDefault()}
      onCloseAutoFocus={() => { restoring.current = true }} onPointerEnter={clearClose} onPointerLeave={leave} onFocusCapture={() => { pinned.current = true; clearClose() }}>
      <div className="mb-3 flex items-center justify-between gap-2"><h4 id={titleId} className="text-sm font-semibold">Thống kê hội thoại</h4><PopoverClose asChild><Button type="button" variant="ghost" size="icon" className="size-11" aria-label="Đóng thống kê hội thoại"><X /></Button></PopoverClose></div>
      <MimiConversationMetrics conversation={conversation} />
    </PopoverContent>
  </Popover>
}
