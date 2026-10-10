import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { fetchMimiEvidence, type MimiConversation } from '@/mimi-api'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'
export function MimiFeedbackEvidence({ conversation, target }: { conversation: MimiConversation; target: { target_type: string; target_id: string } | null | undefined }) {
  const [selected, setSelected] = useState<string | null>(null)
  const ids = [...new Set(conversation.feedback.filter((f) => f.target_type === target?.target_type && f.target_id === target?.target_id).flatMap((f) => f.evidence_bundle_ids ?? []))]
  const active = selected && ids.includes(selected) ? selected : null
  const evidence = useQuery({ queryKey: ['mimi', 'evidence', conversation.id, active], queryFn: () => fetchMimiEvidence(conversation.id, active!), enabled: !!active, ...NO_POLLING_QUERY_OPTIONS })
  return <section className="space-y-2 text-xs" data-testid="mimi-feedback-evidence"><p className="font-semibold">Bằng chứng gắn với mục này</p>{ids.map((id) => <Button key={id} variant="outline" size="sm" onClick={() => setSelected(id)}>Đọc bundle {id.slice(-8)}</Button>)}{!ids.length ? <p className="text-muted-foreground">Chưa có bundle được server xác nhận.</p> : null}{evidence.isFetching ? <p role="status">Đang đọc bằng chứng…</p> : null}{evidence.isError ? <p role="alert" className="text-bad">Không đọc được bundle. Bản ghi feedback vẫn được giữ.</p> : null}{evidence.data ? <details open className="rounded-lg border p-3"><summary className="cursor-pointer font-semibold">Bundle server · trạng thái đầy đủ và nguồn nhân quả</summary><pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(evidence.data, null, 2)}</pre></details> : null}</section>
}
