import { Info } from 'lucide-react'
import type { MimiMessage } from '@/mimi-api'
import { MimiMessageText } from '@/MimiMessageText'
import { isVerifiedServerNotice } from '@/mimi-message-provenance'

export function MimiSystemNotice({ message }: { message: MimiMessage }) {
  if (!isVerifiedServerNotice(message)) return null
  return <article className="min-w-0 rounded-lg bg-muted/60 px-3 py-2 text-muted-foreground" data-testid="mimi-system-notice">
    <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold"><Info className="size-3.5 shrink-0" aria-hidden="true" /><span>Hệ thống</span></div>
    <MimiMessageText text={message.content} />
    <details className="mt-1 text-xs"><summary className="cursor-pointer">Chi tiết</summary>
      <dl className="mt-1 space-y-1 break-all"><div><dt className="font-semibold">Nguồn đã kiểm chứng</dt><dd>{message.provenance?.producer_code} · v1 · event {message.provenance?.event_sequence}</dd></div><div><dt className="font-semibold">Run</dt><dd>{message.run_id}</dd></div></dl>
      <time dateTime={message.created_at}>{new Date(message.created_at).toLocaleString('vi-VN')}</time>
    </details>
  </article>
}
