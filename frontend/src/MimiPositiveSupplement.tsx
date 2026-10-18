import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { saveMimiFeedback, type MimiFeedback } from '@/mimi-api'
import { acknowledgeSupplement, draftKey, emptyDraft, supplementIntent, verifySupplementAck, type SupplementDraft, type SupplementIntent } from '@/mimi-positive-supplement'


export function MimiPositiveSupplement({ conversationId, targetId }: { conversationId: string; targetId: string }) {
  const client = useQueryClient()
  const key = draftKey(conversationId, targetId)
  // Memory-only query data survives dialog/target changes; never browser persistence.
  const { data: draft } = useQuery({ queryKey: key, queryFn: emptyDraft, initialData: emptyDraft, enabled: false, gcTime: Infinity })
  const update = (change: (old: SupplementDraft) => SupplementDraft) => client.setQueryData<SupplementDraft>(key, (old) => change(old ?? emptyDraft()))
  const send = useMutation({
    mutationFn: async (intent: SupplementIntent): Promise<MimiFeedback> => {
      const saved = await saveMimiFeedback(intent.conversationId, { target_type: 'turn', target_id: intent.targetId }, intent.comment, '', intent.clientId)
      return verifySupplementAck(saved, intent)
    },
    onSuccess: (_saved, intent) => {
      client.setQueryData<SupplementDraft>(draftKey(intent.conversationId, intent.targetId), (old) => acknowledgeSupplement(old ?? emptyDraft(), intent))
      void client.invalidateQueries({ queryKey: ['mimi'] })
    },
  })
  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (send.isPending) return
    const intent = supplementIntent(client.getQueryData<SupplementDraft>(key) ?? draft, conversationId, targetId, crypto.randomUUID())
    if (!intent) return
    update((old) => ({ ...old, intent }))
    send.mutate(intent)
  }
  const unknown = !!draft.intent && !send.isPending
  return <form className="space-y-3" onSubmit={submit} data-testid="mimi-positive-supplement">
    <p className="text-sm font-semibold">Bạn có thể chia sẻ thêm (không bắt buộc)</p>
    <div className="grid grid-cols-2 gap-2">{['Rõ ràng', 'Đúng ý', 'Hữu ích', 'Nhanh', 'Dễ hiểu', 'Khác'].map((reason) => <Button type="button" key={reason} variant={draft.reasons.includes(reason) ? 'selected' : 'outline'} size="sm" aria-pressed={draft.reasons.includes(reason)} onClick={() => update((old) => ({ ...old, reasons: old.reasons.includes(reason) ? old.reasons.filter((item) => item !== reason) : [...old.reasons, reason], revision: old.revision + 1, savedRevision: null }))}>{reason}</Button>)}</div>
    <label className="text-sm font-semibold" htmlFor="mimi-positive-detail">Ghi chú phản hồi tích cực</label>
    <Textarea id="mimi-positive-detail" value={draft.text} maxLength={500} onChange={(event) => update((old) => ({ ...old, text: event.target.value, revision: old.revision + 1, savedRevision: null }))} placeholder="Muốn ghi chú thêm? (không bắt buộc)" />
    <p className="text-right text-xs text-muted-foreground">{draft.text.length}/500</p>
    <p className="text-xs text-muted-foreground">Góp ý chi tiết được lưu thành một phản hồi riêng cho đúng mục này. Chỉ gửi khi bạn bấm nút.</p>
    {unknown ? <p role="alert" className="text-sm text-bad">Chưa xác định kết quả lưu. Bản nháp được giữ; thử lại sẽ gửi cùng nội dung và khóa ban đầu.</p> : null}
    {draft.intent && draft.intent.revision !== draft.revision ? <p role="status" className="text-sm text-warn">Có bản gửi trước chưa được đối chiếu. Thử lại bản đó trước; phần bạn vừa sửa vẫn được giữ.</p> : null}
    {draft.savedRevision === draft.revision ? <p role="status" className="text-sm text-ok">Đã lưu góp ý chi tiết</p> : null}
    <Button type="submit" className="min-h-11" disabled={send.isPending || (!draft.intent && !draft.text.trim() && !draft.reasons.length)}>{send.isPending ? 'Đang gửi…' : draft.intent ? 'Thử lại góp ý đã gửi' : 'Gửi bổ sung'}</Button>
  </form>
}
