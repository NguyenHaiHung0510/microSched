import { useId, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { fetchMimiVoicePreferences, saveMimiVoicePreferences } from '@/mimi-api'
import { mimiSessionEpoch } from '@/mimi-session-boundary'
import { MIMI_VOICE_PREFERENCES_KEY as queryKey, publishMimiVoicePreferences } from '@/mimi-voice-preferences'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'

export function MimiVoicePreferences() {
  const client = useQueryClient()
  const [epoch] = useState(() => mimiSessionEpoch(client))
  const id = useId()
  const preferences = useQuery({
    queryKey,
    queryFn: ({ signal }) => fetchMimiVoicePreferences(signal),
    retry: false,
    retryOnMount: false,
    ...NO_POLLING_QUERY_OPTIONS,
  })
  const save = useMutation({
    mutationKey: queryKey,
    mutationFn: saveMimiVoicePreferences,
    retry: false,
    onSuccess: confirmed => publishMimiVoicePreferences(client, epoch, confirmed),
  })
  const failed = preferences.isError || save.isError
  const fastApply = preferences.data?.fast_apply
  return (
    <section className="space-y-2 rounded-lg border p-3" aria-labelledby={`${id}-title`} data-testid="mimi-voice-preferences">
      <h3 className="text-sm font-semibold" id={`${id}-title`}>Giọng nói · Áp dụng nhanh</h3>
      <p id={`${id}-description`} className="text-xs text-muted-foreground">
        Mặc định bật cho Giọng nói. Yêu cầu tạo hoặc sửa rõ ràng cho tối đa 5 Task có thể áp dụng ngay.
        Khi tắt, yêu cầu chưa rõ hoặc tác động trên 5 Task, hãy kiểm tra và duyệt bản xem trước trên màn hình.
        Chat vẫn xác nhận như trước.
      </p>
      {preferences.isPending ? <p role="status" className="text-xs">Đang tải cấu hình giọng nói…</p> : null}
      {fastApply !== undefined && !failed ? (
        <Button type="button" role="switch" aria-checked={fastApply} aria-labelledby={`${id}-title`}
          aria-describedby={`${id}-description`} variant="outline" className="min-h-11"
          disabled={save.isPending || preferences.isFetching} onClick={() => save.mutate(!fastApply)}>
          {fastApply ? 'Đang bật' : 'Đang tắt'}
        </Button>
      ) : null}
      {save.isPending ? <p role="status" className="text-xs">Đang lưu…</p> : null}
      {failed ? <div className="space-y-1">
        <p role="alert" className="text-xs text-bad">{save.isError ? 'Chưa xác nhận được thay đổi. Tải lại để kiểm tra.' : 'Chưa tải được cấu hình giọng nói.'}</p>
        <Button type="button" className="min-h-11" variant="outline" disabled={preferences.isFetching} onClick={() => {
          void preferences.refetch().then(result => { if (result.isSuccess) save.reset() })
        }}>{preferences.isFetching ? 'Đang tải…' : 'Tải lại'}</Button>
      </div> : null}
    </section>
  )
}
