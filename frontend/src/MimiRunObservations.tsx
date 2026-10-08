import type { MimiProviderCall, MimiRunObservation } from '@/mimi-api'

function cost(value: number, unknown: number) {
  return `$${value.toFixed(6)}${unknown ? ` đã biết · ${unknown} call chưa rõ chi phí` : ''}`
}

export function MimiRunObservations({ observation, calls }: {
  observation: MimiRunObservation | undefined
  calls: MimiProviderCall[]
}) {
  const main = calls.filter((call) => (call.purpose ?? 'main') === 'main' && call.paid_dispatch !== false).at(-1)
  const previous = observation?.context_observations.at(-1)
  return <section className="space-y-2 rounded-lg bg-muted/60 p-3 text-xs" aria-label="Quan sát run" data-testid="mimi-run-observations">
    <p className="font-semibold">Input main do provider báo</p>
    <p>{typeof main?.usage.prompt_tokens === 'number' ? `${main.usage.prompt_tokens.toLocaleString('vi-VN')} token` : 'Chưa có input main trong receipt'}</p>
    {previous ? <p className="text-muted-foreground">Input dùng cho quyết định compact ở đầu lượt: {previous.eligible && previous.prompt_tokens !== null ? `${previous.prompt_tokens.toLocaleString('vi-VN')} token` : 'chưa có số phù hợp với context active'}. Ngưỡng {previous.trigger_tokens.toLocaleString('vi-VN')} token · {previous.should_compact ? 'đã yêu cầu compact' : 'chưa có quyết định compact mới'}.</p> : null}
    {observation?.receipts_truncated ? <p>Receipt lịch sử bị giới hạn trong snapshot; tổng chi phí chưa đầy đủ.</p> : null}
    {observation ? <dl className="space-y-1">
      <div><dt className="font-semibold">Chi phí main ({observation.main_calls} call)</dt><dd>{observation.main_calls ? cost(observation.main_known_cost_usd, observation.main_unknown_cost_calls) : 'Chưa dispatch main mới'}</dd></div>
      <div><dt className="font-semibold">Chi phí helper compact ({observation.helper_calls} call)</dt><dd>{cost(observation.helper_known_cost_usd, observation.helper_unknown_cost_calls)}</dd></div>
      <div><dt className="font-semibold">Tổng run {observation.cost_complete ? 'đã báo đủ' : 'đã biết, chưa phải tổng đầy đủ'}</dt><dd>{cost(observation.known_cost_usd, observation.unknown_cost_calls)}</dd></div>
      <div><dt className="font-semibold">Checkpoint active trong lượt</dt><dd>{observation.checkpoint_activations}</dd></div>
      {observation.elapsed_ms !== null ? <div><dt className="font-semibold">Thời gian run</dt><dd>{(observation.elapsed_ms / 1000).toFixed(1)} giây</dd></div> : null}
      {observation.reused_calls ? <div><dt className="font-semibold">Receipt được dùng lại</dt><dd>{observation.reused_calls} · không cộng như dispatch trả phí mới</dd></div> : null}
      {observation.error_code ? <div><dt className="font-semibold">Lý do dừng</dt><dd className="break-all">{observation.error_code}</dd></div> : null}
    </dl> : <p>Chưa có tổng chi phí của run; không suy từ call cuối.</p>}
    <details className="pt-1"><summary className="cursor-pointer font-semibold">Cuộc gọi ({calls.length})</summary>
      <ol className="mt-2 space-y-2">{calls.map((call) => <li key={call.id} className="break-words rounded-lg border p-2">
        <p className="font-semibold">{call.purpose === 'compaction' ? 'Helper compact' : 'Main hội thoại'} · {call.state}</p>
        <p>{call.actual_model ?? call.requested_model ?? 'Model chưa được báo'} · {call.actual_provider ?? 'provider chưa được báo'}</p>
        <p>Input: {typeof call.usage.prompt_tokens === 'number' ? `${call.usage.prompt_tokens.toLocaleString('vi-VN')} token` : 'chưa báo'} · cost: {typeof call.usage.cost === 'number' ? `$${call.usage.cost.toFixed(6)}` : 'chưa rõ'}{call.paid_dispatch === false ? ' · receipt dùng lại' : ''}</p>
      </li>)}</ol>
    </details>
  </section>
}
