import { ChevronDown, Info, X } from 'lucide-react'
import { useId, useRef, useState, useEffect } from 'react'
import type { MimiCapabilities, MimiConversation, MimiProviderCall } from '@/mimi-api'
import { Button } from '@/components/ui/button'
import { Popover, PopoverClose, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { CONTEXT_BUCKETS, lastMeasuredMain, validContextComposition } from '@/mimi-context-metrics'

const format = (value: number | null | undefined) => value == null ? 'Chưa xác định' : value.toLocaleString('vi-VN')
export function ContextMetrics({ calls, capabilities }: { calls: MimiProviderCall[]; capabilities?: MimiCapabilities }) {
  const measured = lastMeasuredMain(calls)
  const actual = measured?.usage.prompt_tokens ?? null
  const compact = capabilities?.compaction_trigger_tokens ?? 272000
  const input = 400000
  const cached = measured?.usage.cached_tokens
  const cache = typeof cached === 'number' && Number.isFinite(cached) && cached >= 0 && actual != null && cached <= actual ? cached : null
  const assembled = calls.filter(c => (c.purpose ?? 'main') === 'main' && c.context_composition).at(-1)
  const composition = assembled?.context_composition
  const validComposition = validContextComposition(composition)
  const reserve = validComposition ? composition?.output_reserve : null
  return <div className="space-y-3" data-testid="mimi-context-composition">
    <p className="text-xs text-muted-foreground">Usage do provider/gateway báo cho call main gần nhất, khác với request tiếp theo chưa gửi.</p>
    <p className="text-xs text-muted-foreground">Nguồn: {measured?.usage_provenance?.source ?? 'receipt chưa khai báo provenance'} · native precision chưa được xác minh riêng; token từng bucket không có trong usage này.</p>
    {measured?.created_at ? <p className="text-xs text-muted-foreground">Call này bắt đầu lúc {new Date(measured.created_at).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })} · GMT+7</p> : null}
    <div className="rounded-xl border bg-muted/20 px-4">
      {[[compact, 'Ngưỡng compact mềm'], [input, 'Mục tiêu operating input']].map(([denominator, label]) => {
        const limit = Number(denominator); const percent = actual == null ? null : Math.round(actual / limit * 100)
        return <section className="border-b py-3" key={label}><div className="flex flex-wrap justify-between gap-1 text-sm font-semibold"><span>{label}</span><span>{percent == null ? 'Chưa xác định' : `${percent}%`}</span></div><p className="text-sm"><strong>{format(actual)}</strong> / {format(limit)} tokens · {actual == null ? 'Chưa có usage' : actual > limit ? `Vượt ${format(actual - limit)}` : `Còn ${format(limit - actual)}`}</p><div className="mimi-context-progress" role={actual == null ? undefined : 'progressbar'} aria-label={String(label)} aria-valuemin={0} aria-valuemax={limit} aria-valuenow={actual == null ? undefined : Math.min(actual, limit)} aria-valuetext={percent == null ? 'Usage chưa xác định' : `${percent}% · usage call trước`}><span style={{ width: `${Math.min(percent ?? 0, 100)}%` }} /></div></section>
      })}
      <section className="border-b py-3 text-sm"><p className="font-semibold">Output reserve <Info className="inline size-3.5" aria-hidden="true" /></p><p>{format(reserve)} tokens · của request đã dựng, tách khỏi input</p></section>
      <section className="py-3 text-sm"><p className="font-semibold">Cached tokens (subset of prompt)</p><p>{format(cache)} / {format(actual)}</p><p className="text-xs text-muted-foreground">Cache là phần nằm trong prompt, không cộng thêm vào tổng.</p></section>
    </div>
    <div className="overflow-hidden rounded-xl border"><table className="w-full text-left text-xs"><caption className="px-3 py-3 text-left text-sm font-semibold">Thành phần context · {validComposition ? 'bytes UTF-8 đo từ request đã dựng' : 'chưa có breakdown được ghi nhận'}</caption><thead className="border-y"><tr><th className="p-3">Thành phần</th><th className="p-3 text-right">Bytes đã serialize</th></tr></thead><tbody>{CONTEXT_BUCKETS.map(([id, label], index) => <tr className="border-b" key={id}><td className="p-3"><span className={`mimi-context-dot mimi-context-bucket-${index}`} aria-hidden="true" />{label}</td><td className="p-3 text-right tabular-nums">{validComposition ? format(composition?.categories?.find(c => c.id === id)?.value) : '—'}</td></tr>)}</tbody><tfoot><tr className="bg-muted/30 font-semibold"><td className="p-3">Tổng bytes đã serialize</td><td className="p-3 text-right">{validComposition ? format(composition?.total) : '—'}</td></tr></tfoot></table></div>
    <p className="text-xs text-muted-foreground">Mỗi bucket đo bytes đã serialize, không phải token do provider báo. Framing native chưa xác định; không phân bổ tổng usage thực vào các bucket. Token ước lượng chỉ hiển thị khi có method và provenance phù hợp.</p>
    {assembled?.created_at ? <p className="text-xs text-muted-foreground">Ước lượng từ request của call bắt đầu lúc {new Date(assembled.created_at).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })} · GMT+7</p> : null}
    <p className="text-xs text-muted-foreground">Request tiếp theo chưa dựng: chưa xác định. Mỗi call có context riêng; đây không phải tổng chi phí hoặc toàn bộ lịch sử server.</p>
  </div>
}

export function MimiContextComposition({ conversation, capabilities }: { conversation: MimiConversation; capabilities?: MimiCapabilities }) {
  const [open, setOpen] = useState(false)
  const pinned = useRef(false)
  const restoring = useRef(false)
  const pointerFocus = useRef(false)
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const titleId = useId()
  const calls = conversation.provider_calls ?? []
  const measured = lastMeasuredMain(calls)
  const actual = measured?.usage.prompt_tokens
  const compact = capabilities?.compaction_trigger_tokens ?? 272000
  const percent = actual == null ? 0 : Math.min(actual / compact * 100, 100)
  function clearClose() { if (closeTimer.current) { clearTimeout(closeTimer.current); closeTimer.current = null } }
  function leave() { clearClose(); if (!pinned.current) closeTimer.current = setTimeout(() => setOpen(false), 240) }
  useEffect(() => () => { if (closeTimer.current) clearTimeout(closeTimer.current) }, [])
  return <Popover open={open} onOpenChange={next => { setOpen(next); if (!next) { pinned.current = false; restoring.current = true } }}>
    <PopoverTrigger asChild><Button type="button" variant="outline" className="mimi-context-meter min-h-11 gap-2" data-testid="mimi-run-context-inspector"
      aria-label={`Ngữ cảnh: ${actual == null ? 'usage chưa xác định' : format(actual) + ' trên ' + format(compact) + ' tokens, call gần nhất'}`}
      onPointerDown={() => { pointerFocus.current = true }} onPointerUp={() => { pointerFocus.current = false }}
      onPointerEnter={event => { if (event.pointerType === 'mouse') { clearClose(); setOpen(true) } }} onPointerLeave={leave}
      onFocus={() => { if (restoring.current) { restoring.current = false; return } if (!pointerFocus.current) setOpen(true) }}
      onClick={event => { event.preventDefault(); clearClose(); pinned.current = true; setOpen(true) }}>
      <span className="mimi-context-ring" style={{ '--context-percent': `${percent}%` } as React.CSSProperties} aria-hidden="true" />
      <span className="flex min-w-0 flex-col text-left text-xs"><span>{actual == null ? `Ngữ cảnh · — / ${Math.round(compact / 1000)}k` : `${Math.round(actual / 1000)}k / ${Math.round(compact / 1000)}k`}</span><span className="mimi-context-progress"><span style={{ width: `${percent}%` }} /></span></span><ChevronDown className="size-3.5" aria-hidden="true" />
    </Button></PopoverTrigger>
    <PopoverContent align="end" aria-labelledby={titleId} onOpenAutoFocus={event => event.preventDefault()}
      onCloseAutoFocus={() => { restoring.current = true }} onPointerEnter={clearClose} onPointerLeave={leave} onFocusCapture={() => { pinned.current = true; clearClose() }}>
      <div className="mb-3 flex items-center justify-between gap-2"><h4 id={titleId} className="mimi-context-composition-title">Context composition <Info className="inline size-4" aria-hidden="true" /></h4><PopoverClose asChild><Button type="button" variant="ghost" size="icon" className="size-11" aria-label="Đóng Context composition"><X /></Button></PopoverClose></div>
      <ContextMetrics calls={calls} capabilities={capabilities} />
    </PopoverContent>
  </Popover>
}
