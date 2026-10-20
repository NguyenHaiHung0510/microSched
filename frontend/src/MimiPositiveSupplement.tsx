import { useEffect, useId, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { saveMimiFeedback, type MimiFeedback } from '@/mimi-api'
import { acknowledgeSupplement, draftKey, emptyDraft, supplementIntent, verifySupplementAck, type SupplementDraft, type SupplementIntent } from '@/mimi-positive-supplement'
import { POSITIVE_SUPPLEMENT_LIMIT } from '@/mimi-owner-feedback'
import { unicodeCodepoints } from '@/mimi-operating-policy'


type Props = { conversationId: string; targetId: string; onLater?: () => void }

export function MimiPositiveSupplement(props: Props) {
  return <SupplementEditor key={JSON.stringify([props.conversationId, props.targetId])} {...props} />
}

function SupplementEditor({ conversationId, targetId, onLater }: Props) {
  const client = useQueryClient()
  const key = draftKey(conversationId, targetId)
  // Memory-only query data survives dialog/target changes; never browser persistence.
  useQuery({ queryKey: key, queryFn: emptyDraft, initialData: emptyDraft, enabled: false, gcTime: Infinity })
  // React must receive the native edit synchronously. Query observer notifications
  // are batched; using their delayed value as the controlled value moves the caret.
  const [draft, setDraft] = useState(() => client.getQueryData<SupplementDraft>(key) ?? emptyDraft())
  const liveDraft = useRef(draft)
  const composing = useRef(false)
  const [isComposing, setIsComposing] = useState(false)
  const inFlight = useRef(false)
  const detailId = useId()
  useEffect(() => client.getQueryCache().subscribe(event => {
    if (event.type !== 'updated' || JSON.stringify(event.query.queryKey) !== JSON.stringify(draftKey(conversationId, targetId))) return
    const next = client.getQueryData<SupplementDraft>(draftKey(conversationId, targetId))
    if (next && next !== liveDraft.current) { liveDraft.current = next; setDraft(next) }
  }), [client, conversationId, targetId])
  const update = (change: (old: SupplementDraft) => SupplementDraft) => {
    const next = change(liveDraft.current)
    liveDraft.current = next
    setDraft(next)
    client.setQueryData<SupplementDraft>(key, next)
  }
  const send = useMutation({
    mutationFn: async (intent: SupplementIntent): Promise<MimiFeedback> => {
      const saved = await saveMimiFeedback(intent.conversationId, { target_type: 'turn', target_id: intent.targetId }, intent.comment, '', intent.clientId)
      return verifySupplementAck(saved, intent)
    },
    onSuccess: (_saved, intent) => {
      client.setQueryData<SupplementDraft>(draftKey(intent.conversationId, intent.targetId), (old) => acknowledgeSupplement(old ?? emptyDraft(), intent))
      void client.invalidateQueries({ queryKey: ['mimi'] })
    },
    onSettled: () => { inFlight.current = false },
  })
  const count = unicodeCodepoints(draft.text)
  const overflow = count > POSITIVE_SUPPLEMENT_LIMIT
  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (send.isPending || inFlight.current || composing.current || (!liveDraft.current.intent && unicodeCodepoints(liveDraft.current.text) > POSITIVE_SUPPLEMENT_LIMIT)) return
    const intent = supplementIntent(liveDraft.current, conversationId, targetId, crypto.randomUUID())
    if (!intent) return
    inFlight.current = true
    update((old) => ({ ...old, intent }))
    send.mutate(intent)
  }
  const unknown = !!draft.intent && !send.isPending
  return <form className="space-y-3" onSubmit={submit} data-testid="mimi-positive-supplement">
    <p className="text-sm font-semibold">Bạn có thể chia sẻ thêm (không bắt buộc)</p>
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">{['Rõ ràng', 'Đúng ý', 'Hữu ích', 'Nhanh', 'Dễ hiểu', 'Khác'].map((reason) => <Button type="button" key={reason} variant={draft.reasons.includes(reason) ? 'selected' : 'outline'} size="sm" className="min-h-8" aria-pressed={draft.reasons.includes(reason)} onClick={() => update((old) => ({ ...old, reasons: old.reasons.includes(reason) ? old.reasons.filter((item) => item !== reason) : [...old.reasons, reason], revision: old.revision + 1, savedRevision: null }))}>{reason}</Button>)}</div>
    <div className="space-y-2">
      <label className="text-sm font-semibold" htmlFor={detailId}>Ghi chú phản hồi tích cực</label>
      <Textarea id={detailId} data-testid="mimi-positive-detail" className="field-sizing-fixed h-44 min-h-40 resize-y bg-card sm:h-48" value={draft.text}
        aria-describedby={`${detailId}-count ${detailId}-help`} aria-invalid={overflow}
        onCompositionStart={() => { composing.current = true; setIsComposing(true) }}
        onCompositionEnd={() => { composing.current = false; setIsComposing(false) }}
        onChange={(event) => { const text = event.target.value; update(old => ({ ...old, text, revision: old.revision + 1, savedRevision: null })) }}
        placeholder="Muốn ghi chú thêm? (không bắt buộc)" />
      <p id={`${detailId}-count`} data-testid="mimi-positive-count" className={`text-right text-xs ${overflow ? 'text-bad' : 'text-muted-foreground'}`}>{count.toLocaleString('vi-VN')}/8.000</p>
      {overflow ? <p role="alert" className="text-xs text-bad">Ghi chú tối đa 8.000 ký tự. Rút ngắn nội dung trước khi gửi.</p> : null}
    </div>
    <p id={`${detailId}-help`} className="text-xs text-muted-foreground">Chỉ gửi khi bạn bấm Gửi bổ sung.</p>
    {unknown ? <p role="alert" className="text-sm text-bad">Chưa xác định kết quả lưu. Bản nháp được giữ; thử lại sẽ gửi cùng nội dung và khóa ban đầu.</p> : null}
    {draft.intent && draft.intent.revision !== draft.revision ? <p role="status" className="text-sm text-warn">Có bản gửi trước chưa được đối chiếu. Thử lại bản đó trước; phần bạn vừa sửa vẫn được giữ.</p> : null}
    {draft.savedRevision === draft.revision ? <p role="status" className="text-sm text-ok">Đã lưu góp ý chi tiết</p> : null}
    <div className="flex flex-wrap justify-end gap-2">
      {onLater ? <Button type="button" variant="outline" className="min-h-11" onClick={onLater}>Để sau</Button> : null}
      <Button type="submit" data-testid="mimi-positive-submit" className="min-h-11" disabled={send.isPending || isComposing || (!draft.intent && (overflow || (!draft.text.trim() && !draft.reasons.length)))}>{send.isPending ? 'Đang gửi…' : draft.intent ? 'Thử lại góp ý đã gửi' : 'Gửi bổ sung'}</Button>
    </div>
  </form>
}
