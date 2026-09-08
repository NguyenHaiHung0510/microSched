import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '@/api'
import { Button } from '@/components/ui/button'
import { ensurePushSubscription } from '@/push-subscription'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'
import { reminderKey } from '@/reminder-ui'

export function ReminderDevices() {
  const client = useQueryClient()
  const devices = useQuery({ queryKey: [...reminderKey, 'devices'],
    queryFn: ({ signal }) => apiRequest<{ registered_devices: number }>('/api/reminders/device-status', { signal }),
    ...NO_POLLING_QUERY_OPTIONS })
  const register = useMutation({ mutationFn: ensurePushSubscription,
    onSuccess: () => { void client.invalidateQueries({ queryKey: [...reminderKey, 'devices'] }) } })
  return <div className="space-y-2 text-sm">
    {devices.data?.registered_devices === 0 && <p role="status">Chưa có thiết bị nhận. Bạn có thể lưu lịch, rồi bật nhận thông báo trước giờ nhắc.</p>}
    <Button type="button" size="lg" variant="outline" disabled={register.isPending} onClick={() => register.mutate()}>
      {register.isPending ? 'Đang bật thông báo…' : 'Bật nhận trên thiết bị này'}</Button>
    {register.isSuccess && <p role="status">Thiết bị này đã đăng ký nhận thông báo.</p>}
    {register.isError && <p role="alert" className="text-bad">{register.error.message}</p>}
  </div>
}
