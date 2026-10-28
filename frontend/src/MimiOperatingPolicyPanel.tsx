import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { ApiError } from '@/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { fetchMimiOperatingPolicy, saveMimiOperatingPolicy, type MimiOperatingPolicy, type MimiModelProfile } from '@/mimi-api'
import { operatingPolicyErrors } from '@/mimi-operating-policy'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'

export function MimiOperatingPolicyPanel({ profiles, enabled }: { profiles: MimiModelProfile[]; enabled: boolean }) {
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['mimi', 'operating-policy'], queryFn: fetchMimiOperatingPolicy, enabled, retry: false, ...NO_POLLING_QUERY_OPTIONS })
  const [draft, setDraft] = useState<MimiOperatingPolicy | null>(null)
  const [review, setReview] = useState(false)
  const [validated, setValidated] = useState(false)
  const [needsRebase, setNeedsRebase] = useState(false)
  const errorRef = useRef<HTMLDivElement>(null)
  const selected = draft ?? query.data?.policy
  const errors = selected ? operatingPolicyErrors(selected) : []
  const save = useMutation({ mutationFn: saveMimiOperatingPolicy, onSuccess: value => {
    client.setQueryData(['mimi', 'operating-policy'], value); setDraft(null); setReview(false); setNeedsRebase(false)
    void client.invalidateQueries({ queryKey: ['mimi', 'provider-pool'] })
  }, onError: error => { if (error instanceof ApiError && error.status === 409) setNeedsRebase(true) } })
  function update(next: MimiOperatingPolicy) { setDraft(next); setReview(false); save.reset() }
  function check() { setValidated(true); if (errors.length) requestAnimationFrame(() => errorRef.current?.focus()); else setReview(true) }
  if (!enabled) return null
  if (!selected) return <section className="rounded-xl border p-4"><p role={query.isError ? 'alert' : 'status'}>{query.isError ? 'Không tải được giới hạn nhập và trần giá.' : 'Đang tải giới hạn nhập và trần giá…'}</p>{query.isError ? <Button variant="outline" className="mt-3 min-h-11" onClick={() => void query.refetch()}>Tải lại</Button> : null}</section>
  const changePrice = (model: string, kind: 'prompt' | 'completion', value: string) => update({ ...selected, prices: { ...selected.prices, [model]: { ...selected.prices[model], [kind]: value } } })
  return <section className="space-y-4" aria-label="Giới hạn nhập và trần giá Mimi" data-testid="mimi-operating-policy-panel">
    <div className="rounded-xl border p-4"><h3 className="text-lg font-bold">Giới hạn nhập tin nhắn</h3><p className="mt-1 text-sm text-muted-foreground">Giữ nguyên bản nháp khi vượt giới hạn; bạn kiểm và chỉnh trước khi gửi.</p><label className="mt-3 block text-sm font-semibold" htmlFor="mimi-input-codepoints">Unicode codepoints mỗi tin nhắn</label><Input id="mimi-input-codepoints" className="mt-1 min-h-11" inputMode="numeric" value={Number.isNaN(selected.input_codepoints) ? '' : String(selected.input_codepoints)} disabled={save.isPending} onChange={e => update({ ...selected, input_codepoints: /^\d+$/.test(e.target.value) ? Number(e.target.value) : Number.NaN })} onBlur={() => setValidated(true)} aria-describedby="mimi-input-policy-help" /><p id="mimi-input-policy-help" className="mt-2 text-xs text-muted-foreground">1.000–100.000 · default 50.000 codepoints. Emoji và dấu được đếm theo Unicode codepoint.</p></div>
    <div className="rounded-xl border p-4"><h3 className="text-lg font-bold">Trần giá theo model</h3><p className="my-2 text-sm text-muted-foreground">Trần tuyệt đối do bạn đặt · USD / 1 triệu tokens. Đây là giới hạn được lưu, không phải báo giá live.</p><div className="grid gap-3 sm:grid-cols-2">{Object.entries(selected.prices).map(([model, caps], index) => <fieldset className="min-w-0 rounded-lg border p-3" key={model}><legend className="px-1 text-sm font-semibold">{profiles.find(p => p.model === model)?.label ?? model}</legend><div className="grid grid-cols-2 gap-3">{(['prompt', 'completion'] as const).map(kind => <div key={kind}><label className="text-xs font-semibold" htmlFor={`mimi-price-${index}-${kind}`}>{kind === 'prompt' ? 'Input' : 'Output'} · USD / 1M</label><Input id={`mimi-price-${index}-${kind}`} className="mt-1 min-h-11" value={caps[kind]} inputMode="decimal" disabled={save.isPending} onChange={e => changePrice(model, kind, e.target.value)} onBlur={() => setValidated(true)} /></div>)}</div></fieldset>)}</div><details className="mt-3"><summary className="cursor-pointer text-sm font-semibold">Điền mẫu peak +20% thủ công</summary><p className="my-2 text-sm">Ví dụ reference0,30 /1,20 →0,36 /1,44 USD/1M cho DeepSeek. Chỉ điền vào bản nháp để bạn kiểm; không tự lấy giá thị trường.</p><Button type="button" variant="outline" className="min-h-11" disabled={save.isPending} onClick={() => update({ ...selected, prices: { ...selected.prices, [profiles.find(p => p.id === 'deepseek')?.model ?? 'deepseek/deepseek-v4.1-flash-1017']: { prompt: '0.36', completion: '1.44' } } })}>Điền mẫu vào bản nháp</Button></details></div>
    <p className="rounded-lg bg-accent p-3 text-sm">Áp dụng cho wire tiếp theo chưa gửi, gồm helper/resume. Call đã gửi vẫn có thể phát sinh phí theo snapshot trước đó. Preview đang chờ Confirm giữ nguyên.</p>
    {validated && errors.length ? <div ref={errorRef} tabIndex={-1} role="alert" className="rounded-lg border border-bad bg-bad-bg p-3 text-sm text-bad">{errors.map(e => <p key={e}>{e}</p>)}</div> : null}
    {save.isError ? <div role="alert" className="space-y-2 text-sm text-bad"><p>{needsRebase ? 'Revision đã đổi trên server. Bản nháp được giữ; tải revision mới rồi kiểm lại trước khi lưu.' : 'Chưa lưu được. Bản nháp vẫn được giữ.'}</p>{needsRebase ? <Button variant="outline" disabled={query.isFetching} className="min-h-11" onClick={() => void query.refetch().then(result => { if (result.data) { setDraft({ ...selected, revision: result.data.policy.revision }); setNeedsRebase(false); setReview(false); save.reset() } })}>Tải revision mới, giữ bản nháp</Button> : null}</div> : null}
    {review ? <div className="space-y-3 rounded-xl border bg-muted/30 p-4"><h4 className="text-base font-bold">Kiểm tra trước khi áp dụng</h4><p className="text-sm">Revision kỳ vọng {selected.revision} · {selected.input_codepoints.toLocaleString('vi-VN')} codepoints</p><ul className="space-y-1 text-xs">{Object.entries(selected.prices).map(([model, caps]) => <li key={model} className="break-words">{profiles.find(p => p.model === model)?.label ?? model}: input{caps.prompt}, output{caps.completion} USD/1M</li>)}</ul><Button className="min-h-11" disabled={save.isPending || needsRebase || errors.length > 0} onClick={() => save.mutate(selected)}>{save.isPending ? 'Đang lưu…' : 'Lưu revision mới'}</Button><Button className="ml-2 min-h-11" variant="outline" disabled={save.isPending} onClick={() => setReview(false)}>Quay lại chỉnh</Button></div> : <div className="flex flex-wrap gap-2"><Button className="min-h-11" disabled={!draft || save.isPending || needsRebase} onClick={check}>Kiểm tra thay đổi</Button><Button className="min-h-11" variant="outline" disabled={save.isPending} onClick={() => { setDraft(null); setReview(false); setNeedsRebase(false); setValidated(false); save.reset() }}>Khôi phục cấu hình đã tải</Button></div>}
    {save.isSuccess ? <p role="status" className="text-sm text-ok">Đã lưu revision {query.data?.policy.revision}, áp dụng cho wire mới.</p> : null}
  </section>
}
