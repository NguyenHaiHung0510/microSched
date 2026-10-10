import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Bell } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { fetchMimiAttention, acknowledgeMimiAttention, fetchMimiCapabilities, readMimiDevicePreference, saveMimiDevicePreference, type MimiDeviceProof } from '@/mimi-api'
import { ensurePushSubscription, readExistingPushProof } from '@/push-subscription'
import { selectMimiConversation } from '@/mimi-selection'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'

export function MimiNotifications({ conversationId }: { conversationId: string | null }) {
  const client = useQueryClient()
  const [gestureProof, setGestureProof] = useState<MimiDeviceProof | null>(null)
  const capabilities = useQuery({ queryKey: ['mimi', 'capabilities'], queryFn: fetchMimiCapabilities, ...NO_POLLING_QUERY_OPTIONS })
  const enabled = capabilities.data?.notifications_enabled === true
  const attention = useQuery({ queryKey: ['mimi', 'attention'], queryFn: fetchMimiAttention, enabled, ...NO_POLLING_QUERY_OPTIONS })
  const preferenceKey = ['mimi', 'device-preference']
  const preference = useQuery({ queryKey: preferenceKey, queryFn: async () => { const proof = gestureProof ?? await readExistingPushProof(); return proof ? { proof, preference: await readMimiDevicePreference(proof) } : null }, enabled, ...NO_POLLING_QUERY_OPTIONS, retry: false })
  const change = useMutation({
    mutationFn: async (turnOn: boolean) => {
      const proof = preference.data?.proof ?? gestureProof ?? (turnOn ? await ensurePushSubscription() : null)
      if (!proof) throw new Error('Chưa có proof thiết bị để đổi trạng thái.')
      setGestureProof(proof)
      const current = await readMimiDevicePreference(proof)
      return { proof, preference: await saveMimiDevicePreference(proof, turnOn, current.revision) }
    },
    onSuccess: (value) => client.setQueryData(preferenceKey, value),
    onError: () => { void client.invalidateQueries({ queryKey: preferenceKey }) },
  })
  const ack = useMutation({ mutationFn: acknowledgeMimiAttention, onSuccess: () => void client.invalidateQueries({ queryKey: ['mimi', 'attention'] }) })
  if (!enabled) return null
  const rows = (attention.data ?? []).filter((row) => !conversationId || row.conversation_id === conversationId)
  const pref = preference.data?.preference
  return <section className="mimi-attention space-y-2 rounded-xl p-3" data-testid="mimi-attention"><h3 className="flex items-center gap-2 text-sm font-semibold"><Bell className="size-4" />Thông báo Mimi</h3><details><summary className="cursor-pointer text-xs font-semibold">Thiết bị: {preference.isFetching ? 'đang đọc' : preference.isError ? 'chưa xác định' : pref?.enabled ? 'đã bật theo server' : 'mặc định tắt'}</summary><p className="mt-2 text-xs text-muted-foreground">Thông báo trong app luôn có. Bật đẩy cho thiết bị này cần thao tác của bạn và proof đăng ký. Không tự xin quyền khi tải trang.</p><div className="mt-2 flex flex-wrap gap-1"><Button size="sm" variant="outline" disabled={change.isPending || preference.isFetching} onClick={() => change.mutate(!pref?.enabled)}>{pref?.enabled ? 'Tắt trên thiết bị này' : 'Bật trên thiết bị này'}</Button><Button size="sm" variant="ghost" disabled={preference.isFetching || change.isPending} onClick={() => void preference.refetch()}>Đọc lại trạng thái</Button></div>{change.isError ? <p role="alert" className="mt-2 text-xs text-bad">Chưa xác định kết quả thay đổi. Đọc lại proof trước khi thao tác tiếp; không tự thử lại.</p> : null}{pref ? <p className="mt-2 text-xs">Revision {pref.revision ?? 'chưa đăng ký'} · {pref.enabled ? 'bật' : 'tắt'}</p> : null}</details>
  {attention.isError ? <p role="alert" className="text-xs text-bad">Chưa đọc được thông báo.</p> : null}<Button size="sm" variant="ghost" disabled={attention.isFetching} onClick={() => void attention.refetch()}>Làm mới</Button><ul className="space-y-2">{rows.slice(0, 3).map((row) => <li key={row.id} className="rounded-lg bg-muted p-2 text-xs"><p className="font-semibold">{row.title}{row.unread ? ' · mới' : ''}</p><p className="mt-1 line-clamp-3 whitespace-pre-wrap break-words">{row.body}</p><p className="mt-1 text-muted-foreground">{row.kind === 'preview' && new Date(row.expires_at) <= new Date() ? 'Preview có thể đã hết hạn; mở để đọc trạng thái.' : 'Mở hội thoại để đọc trạng thái hiện tại.'}</p><div className="mt-1 flex flex-wrap gap-1"><Button size="sm" variant="outline" onClick={() => selectMimiConversation(row.conversation_id)}>Mở hội thoại</Button>{row.unread ? <Button size="sm" variant="ghost" disabled={ack.isPending} onClick={() => ack.mutate(row.id)}>Đánh dấu đã đọc</Button> : null}</div></li>)}</ul>{ack.isError ? <p role="alert" className="text-xs text-bad">Chưa xác nhận trạng thái đã đọc.</p> : null}</section>
}
