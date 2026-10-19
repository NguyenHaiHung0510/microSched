import { Button } from '@/components/ui/button'
import { Copy, Info, ThumbsDown, ThumbsUp } from 'lucide-react'
import { toast } from 'sonner'
import type { MimiMessage } from '@/mimi-api'
import { MimiMessageText } from '@/MimiMessageText'
import { isVerifiedServerNotice, systemNoticeText } from '@/mimi-message-provenance'

export function MimiSystemNotice({ message, onFeedback, feedbackPending = false }: { message: MimiMessage; onFeedback?: (mood: 'positive' | 'negative') => void; feedbackPending?: boolean }) {
  if (!isVerifiedServerNotice(message)) return null
  const text = systemNoticeText(message)
  return <article className="mimi-system-notice min-w-0 rounded-xl border bg-muted/60 text-muted-foreground" data-testid="mimi-system-notice">
    <Info className="mt-2 size-4 shrink-0" aria-hidden="true" />
    <details className="min-w-0 flex-1 text-xs"><summary className="cursor-pointer py-2 [overflow-wrap:anywhere]"><span className="font-semibold">Hệ thống</span> · {text.split(/(?<=[.!?])\s/)[0]}</summary>
      <div className="pb-2"><MimiMessageText text={text} /></div>
      <dl className="space-y-1 break-all"><div><dt className="font-semibold">Nguồn đã kiểm chứng</dt><dd>{message.provenance?.producer_code} · v1 · event {message.provenance?.event_sequence}</dd></div><div><dt className="font-semibold">Run</dt><dd>{message.run_id}</dd></div></dl>
      <time dateTime={message.created_at}>{new Date(message.created_at).toLocaleString('vi-VN')}</time>
    </details>
    <div className="mimi-system-notice-actions flex shrink-0 gap-1" aria-label={`Hành động trạng thái hệ thống ${message.sequence}`}>
      <Button type="button" size="icon" variant="ghost" aria-label={`Sao chép trạng thái hệ thống ${message.sequence}`} onClick={() => { void navigator.clipboard.writeText(text).then(() => toast.success('Đã sao chép', { duration: 2000 })).catch(() => toast.error('Chưa sao chép được', { duration: 2000 })) }}><Copy className="size-4" aria-hidden="true" /></Button>
      {onFeedback ? <><Button type="button" size="icon" variant="ghost" disabled={feedbackPending} onClick={() => onFeedback('positive')} aria-label={`Hữu ích · trạng thái hệ thống ${message.sequence}`}><ThumbsUp className="size-4" aria-hidden="true" /></Button><Button type="button" size="icon" variant="ghost" disabled={feedbackPending} onClick={() => onFeedback('negative')} aria-label={`Chưa tốt · trạng thái hệ thống ${message.sequence}`}><ThumbsDown className="size-4" aria-hidden="true" /></Button></> : null}
    </div>
  </article>
}
