import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, Check, LoaderCircle, MessageSquareWarning, ReceiptText, Send, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { ApiError, TimeoutError } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import {
  createMimiConversation,
  decideMimiChangeSet,
  fetchCurrentMimiConversation,
  saveMimiFeedback,
  sendMimiMessage,
  type MimiChangeSet,
  type MimiConversation,
} from '@/mimi-api'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'

const QUERY_KEY = ['mimi', 'current'] as const

function errorMessage(error: unknown): string {
  if (error instanceof TimeoutError) return error.message
  if (error instanceof ApiError) {
    if (error.status === 409) return 'Preview hoặc conversation đã thay đổi. Tải lại trước khi thử tiếp.'
    if (error.status === 410) return 'Preview đã hết hạn. Gửi lại yêu cầu để Mimi tạo preview mới.'
    return error.message
  }
  if (error instanceof TypeError) return 'Không kết nối được. Nội dung bạn nhập vẫn được giữ lại.'
  return 'Có lỗi chưa xác định. Thử lại sau.'
}

function expiryLabel(value: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
    day: '2-digit',
    month: '2-digit',
  }).format(new Date(value))
}

function ChangeSetPreview({
  changeSet,
  pending,
  error,
  onDecision,
}: {
  changeSet: MimiChangeSet
  pending: boolean
  error: string | null
  onDecision: (decision: 'confirm' | 'reject') => void
}) {
  const task = changeSet.operation.args
  return (
    <Card data-testid="mimi-change-set" className="border-primary/20 bg-primary/5">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <Badge>Chờ xác nhận</Badge>
          <Badge variant="outline">STANDARD</Badge>
          <Badge variant="outline">task.create.v1</Badge>
        </div>
        <CardTitle>Tạo Task “{task.title}”</CardTitle>
        <CardDescription>
          Mimi cần xác nhận vì thao tác này sẽ ghi dữ liệu thật vào microSched.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Đích</dt>
            <dd>Task công khai · trạng thái mở</dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Hết hạn</dt>
            <dd>{expiryLabel(changeSet.expires_at)}</dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Nguồn</dt>
            <dd>Conversation hiện tại · không dùng dữ liệu PRIVATE</dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Digest</dt>
            <dd className="break-all font-mono text-xs">{changeSet.digest.slice(0, 16)}…</dd>
          </div>
        </dl>
        {error ? <p role="alert" className="text-sm text-bad">{error}</p> : null}
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button
            className="min-h-11"
            disabled={pending}
            onClick={() => onDecision('confirm')}
          >
            {pending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : <Check />}
            Xác nhận tạo Task
          </Button>
          <Button
            className="min-h-11"
            variant="outline"
            disabled={pending}
            onClick={() => onDecision('reject')}
          >
            <X />
            Từ chối
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export function MimiScreen({ onOpenTasks }: { onOpenTasks: () => void }) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState('')
  const [online, setOnline] = useState(() => navigator.onLine)
  const [feedbackDraft, setFeedbackDraft] = useState('')
  const [feedbackClientId, setFeedbackClientId] = useState<string | null>(null)

  useEffect(() => {
    const connected = () => setOnline(true)
    const disconnected = () => setOnline(false)
    window.addEventListener('online', connected)
    window.addEventListener('offline', disconnected)
    return () => {
      window.removeEventListener('online', connected)
      window.removeEventListener('offline', disconnected)
    }
  }, [])

  const conversation = useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchCurrentMimiConversation,
    ...NO_POLLING_QUERY_OPTIONS,
  })

  const createConversation = useMutation({
    mutationFn: createMimiConversation,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: QUERY_KEY }),
  })

  const send = useMutation({
    mutationFn: ({ current, content, clientId }: {
      current: MimiConversation
      content: string
      clientId: string
    }) => sendMimiMessage(current.id, content, current.generation, clientId),
    onSuccess: (data) => {
      queryClient.setQueryData(QUERY_KEY, data)
      setDraft('')
    },
  })

  const decision = useMutation({
    mutationFn: ({ changeSet, choice, key }: {
      changeSet: MimiChangeSet
      choice: 'confirm' | 'reject'
      key: string
    }) => decideMimiChangeSet(changeSet, choice, key),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: QUERY_KEY }),
  })

  const feedback = useMutation({
    mutationFn: ({ current, receiptId, comment, clientId }: {
      current: MimiConversation
      receiptId: string
      comment: string
      clientId: string
    }) => saveMimiFeedback(current.id, receiptId, comment, clientId),
    onSuccess: () => {
      setFeedbackDraft('')
      setFeedbackClientId(null)
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
  })

  const current = conversation.data
  const pendingChangeSet = useMemo(
    () => [...(current?.change_sets ?? [])].reverse().find((item) => item.state === 'pending'),
    [current?.change_sets],
  )
  const latestReceipt = current?.receipts.at(-1)
  const latestRun = current?.runs.at(-1)

  function submitMessage(event: React.FormEvent) {
    event.preventDefault()
    if (!current || !draft.trim() || send.isPending || !online) return
    send.mutate({ current, content: draft, clientId: crypto.randomUUID() })
  }

  function submitFeedback(event: React.FormEvent) {
    event.preventDefault()
    if (!current || !latestReceipt || !feedbackDraft.trim() || feedback.isPending) return
    const clientId = feedbackClientId ?? crypto.randomUUID()
    setFeedbackClientId(clientId)
    feedback.mutate({ current, receiptId: latestReceipt.id, comment: feedbackDraft, clientId })
  }

  if (conversation.isPending) {
    return <p role="status" className="py-12 text-center text-sm text-muted-foreground">Đang mở Mimi…</p>
  }

  if (conversation.isError) {
    return (
      <Card role="alert" className="mx-auto max-w-lg">
        <CardHeader>
          <CardTitle>Không tải được Mimi</CardTitle>
          <CardDescription>{errorMessage(conversation.error)}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" onClick={() => void conversation.refetch()}>Thử lại</Button>
        </CardContent>
      </Card>
    )
  }

  if (!current) {
    return (
      <Card className="mx-auto max-w-xl py-10 text-center">
        <CardHeader>
          <Bot className="mx-auto size-10 text-primary" aria-hidden="true" />
          <CardTitle>Mimi sẵn sàng ở chế độ local</CardTitle>
          <CardDescription>
            P1 chỉ đọc Task STANDARD và luôn cho bạn xem preview trước khi ghi.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {createConversation.isError ? <p role="alert" className="mb-3 text-sm text-bad">{errorMessage(createConversation.error)}</p> : null}
          <Button
            className="min-h-11"
            disabled={createConversation.isPending || !online}
            onClick={() => createConversation.mutate()}
          >
            {createConversation.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : <Bot />}
            Bắt đầu conversation STANDARD
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <section className="space-y-4" aria-labelledby="mimi-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="mimi-title" className="text-xl font-extrabold text-primary">Mimi</h2>
          <p className="text-sm text-muted-foreground">Conversation STANDARD · deterministic local route</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={online ? 'secondary' : 'destructive'}>{online ? 'Online' : 'Offline'}</Badge>
          {latestRun ? <Badge variant="outline">{latestRun.state.replaceAll('_', ' ')}</Badge> : null}
        </div>
      </div>

      {!online ? (
        <p role="status" className="rounded-lg bg-warn-bg p-3 text-sm text-foreground">
          Bạn đang offline. Draft được giữ trên màn hình và chưa được lưu ở trình duyệt.
        </p>
      ) : null}

      <div className="max-h-[28rem] space-y-3 overflow-y-auto rounded-xl bg-muted/50 p-3" data-testid="mimi-messages">
        {current.messages.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Hãy nói Task bạn muốn tạo.</p>
        ) : current.messages.map((message) => (
          <article
            key={message.id}
            className={message.role === 'user'
              ? 'ml-auto max-w-[88%] rounded-xl bg-primary px-4 py-3 text-primary-foreground'
              : 'mr-auto max-w-[88%] rounded-xl bg-card px-4 py-3 ring-1 ring-foreground/10'}
          >
            <p className="whitespace-pre-wrap break-words text-sm">{message.content}</p>
          </article>
        ))}
      </div>

      {pendingChangeSet ? (
        <ChangeSetPreview
          changeSet={pendingChangeSet}
          pending={decision.isPending}
          error={decision.isError ? errorMessage(decision.error) : null}
          onDecision={(choice) => decision.mutate({
            changeSet: pendingChangeSet,
            choice,
            key: crypto.randomUUID(),
          })}
        />
      ) : null}

      {latestReceipt ? (
        <Card data-testid="mimi-receipt">
          <CardHeader>
            <div className="flex items-center gap-2">
              <ReceiptText className="size-5 text-ok" aria-hidden="true" />
              <CardTitle>Task đã được tạo</CardTitle>
            </div>
            <CardDescription className="break-all">Receipt {latestReceipt.id}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button variant="outline" onClick={onOpenTasks}>Mở Task</Button>
            <form className="space-y-2 border-t pt-4" onSubmit={submitFeedback}>
              <label htmlFor="mimi-feedback" className="text-sm font-semibold">Feedback về kết quả này</label>
              <Textarea
                id="mimi-feedback"
                value={feedbackDraft}
                maxLength={10_000}
                placeholder="Điều gì chưa đúng hoặc cần rõ hơn?"
                onChange={(event) => setFeedbackDraft(event.target.value)}
              />
              {feedback.isError ? (
                <p role="alert" className="flex items-center gap-2 text-sm text-bad">
                  <MessageSquareWarning className="size-4" />
                  Chưa lưu feedback. {errorMessage(feedback.error)}
                </p>
              ) : null}
              {current.feedback.some((item) => item.target_id === latestReceipt.id) ? (
                <p role="status" className="text-sm text-ok">Feedback đã lưu · còn mở để xử lý.</p>
              ) : null}
              <Button type="submit" variant="secondary" disabled={!feedbackDraft.trim() || feedback.isPending}>
                {feedback.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : null}
                Lưu feedback
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : null}

      <form className="space-y-2" onSubmit={submitMessage}>
        <label htmlFor="mimi-message" className="text-sm font-semibold">Nhắn Mimi</label>
        <Textarea
          id="mimi-message"
          data-testid="mimi-input"
          value={draft}
          maxLength={12_000}
          placeholder="Ví dụ: Tạo task chuẩn bị demo vào thứ Sáu"
          disabled={send.isPending}
          onChange={(event) => setDraft(event.target.value)}
        />
        {send.isError ? <p role="alert" className="text-sm text-bad">{errorMessage(send.error)}</p> : null}
        <div className="flex items-center justify-between gap-3">
          <p aria-live="polite" className="text-xs text-muted-foreground">
            {send.isPending ? 'Mimi đang tạo preview…' : 'Không có thay đổi nào được ghi khi chưa xác nhận.'}
          </p>
          <Button type="submit" className="min-h-11" disabled={!draft.trim() || send.isPending || !online}>
            {send.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : <Send />}
            Gửi
          </Button>
        </div>
      </form>

      {current.events.length ? (
        <details className="rounded-lg border p-3 text-sm">
          <summary className="cursor-pointer font-semibold">Execution events ({current.events.length})</summary>
          <ol className="mt-3 space-y-1 text-xs text-muted-foreground">
            {current.events.slice(-30).map((event) => (
              <li key={event.id}>{event.kind}</li>
            ))}
          </ol>
        </details>
      ) : null}
    </section>
  )
}
