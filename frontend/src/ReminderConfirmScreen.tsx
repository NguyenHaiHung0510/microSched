import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { apiRequest } from '@/api'
import { Card } from '@/components/ui/card'
import { navigate, useLocation } from '@/lib/route'
import { uuidv7 } from '@/lib/uuidv7'
import type { PrivateSessionState } from '@/private-gate'

interface ConfirmResponse {
  confirmed_entry_id: string
  created: boolean
}

export function ReminderConfirmScreen() {
  const location = useLocation()
  const [entryId] = useState(() => uuidv7())
  const [occurredAt] = useState(() => new Date().toISOString())

  const searchParams = new URLSearchParams(
    location.includes('?') ? location.slice(location.indexOf('?')) : ''
  )
  const { data: session } = useQuery<PrivateSessionState>({
    queryKey: ['session'],
    queryFn: () => apiRequest('/api/private/session'),
  })
  const dispatchId = searchParams.get('dispatch')

  const confirmMutation = useMutation({
    mutationFn: async () => {
      if (!dispatchId) {
        throw new Error('Thi?u dispatch ID')
      }
      return apiRequest<ConfirmResponse>(
        `/api/reminder-dispatch/${dispatchId}/confirm`,
        {
          method: 'POST',
          body: JSON.stringify({
            entry_id: entryId,
            occurred_at: occurredAt,
          }),
        }
      )
    },
    onSuccess: (data) => {
      if (data.created) {
        toast.success('?? ghi nh?n u?ng thu?c', { duration: 10000 })
      } else {
        toast.info('L?n u?ng n?y ?? ???c ghi t? tr??c', { duration: 10000 })
      }
      navigate('/')
    },
    onError: (error) => {
      toast.error(error.message || 'Kh?ng th? x?c nh?n l?i nh?c', { duration: 10000 })
      navigate('/')
    },
  })

  useEffect(() => {
    if (dispatchId && !confirmMutation.isPending && !confirmMutation.isSuccess && !confirmMutation.isError) {
      confirmMutation.mutate()
      if (session && !session.private_until) {
        toast.info('Kho?n m?c ri?ng t?: H?y m? Ch? ?? Ri?ng t? (m? PIN) ?? xem chi ti?t.', {
          duration: 12000,
        })
      }
    } else if (!dispatchId) {
      toast.error('Li?n k?t nh?c nh? kh?ng h?p l?', { duration: 10000 })
      navigate('/')
    }
  }, [dispatchId, confirmMutation, session])

  return (
    <Card className="mx-auto max-w-lg gap-4 rounded-lg bg-card p-6 shadow-2 ring-0" role="status">
      <h1 className="text-xl font-extrabold tracking-tight text-primary">microSched</h1>
      <p className="text-sm text-muted-foreground">?ang x?c nh?n l?i nh?c u?ng thu?c?</p>
    </Card>
  )
}
