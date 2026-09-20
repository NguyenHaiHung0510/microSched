import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, CircleDot, LoaderCircle, MessageSquareWarning, ReceiptText, RotateCcw, Send, Square, Wifi, WifiOff, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { MimiAvatar, type MimiState } from '@/components/brand'
import { ApiError, TimeoutError } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import {
  createMimiConversation,
  cancelMimiRun,
  decideMimiChangeSet,
  fetchMimiConversation,
  fetchCurrentMimiConversation,
  reconcileMimiRun,
  resumeMimiRun,
  saveMimiFeedback,
  streamMimiMessage,
  type MimiChangeSet,
  type MimiConversation,
} from '@/mimi-api'
import { mimiRunLabel, mimiTaskScheduleLabel } from '@/mimi-presentation'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'

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

function requestsPreviewRevision(content: string): boolean {
  const normalized = content.trim().toLocaleLowerCase('vi-VN').replace(/\s+/g, ' ')
  return ['sửa preview', 'chỉnh preview', 'cập nhật preview', 'update preview', 'revise preview']
    .some((prefix) => normalized.startsWith(prefix))
}

function useElapsed(startedAt: number | null, active: boolean): number {
  const [now, setNow] = useState(0)
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => setNow(Date.now()), 1_000)
    return () => window.clearInterval(timer)
  }, [active])
  return startedAt ? Math.max(0, Math.floor((now - startedAt) / 1_000)) : 0
}

function elapsedLabel(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  return `${minutes.toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`
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
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Lịch Task</dt>
            <dd>{mimiTaskScheduleLabel(task)}</dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Preview hết hạn</dt>
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

export function MimiScreen({
  onOpenTasks,
  variant = 'workspace',
  conversationId,
  onConversationCreated,
}: {
  onOpenTasks: () => void
  variant?: 'workspace' | 'dock'
  conversationId?: string | null
  onConversationCreated?: (conversationId: string) => void
}) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState('')
  const [online, setOnline] = useState(() => navigator.onLine)
  const [feedbackDraft, setFeedbackDraft] = useState('')
  const [feedbackClientId, setFeedbackClientId] = useState<string | null>(null)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [runStartedAt, setRunStartedAt] = useState<number | null>(null)
  const [runStage, setRunStage] = useState('Sẵn sàng')
  const [streamedText, setStreamedText] = useState('')

  function handleStreamEvent({ event, data }: { event: string; data: Record<string, unknown> }) {
    if (event === 'run.reserved' && typeof data.run_id === 'string') {
      setActiveRunId(data.run_id)
      setRunStage('Đã nhận yêu cầu')
    } else if (event === 'context.tasks_read') setRunStage('Đã đọc Task STANDARD')
    else if (event === 'provider.connected') setRunStage('Đã kết nối provider')
    else if (event === 'assistant.delta') {
      setRunStage('Mimi đang trả lời')
      if (typeof data.payload === 'object' && data.payload && 'text' in data.payload) {
        const text = (data.payload as { text?: unknown }).text
        if (typeof text === 'string') setStreamedText((currentText) => currentText + text)
      }
    } else if (event === 'provider.succeeded') setRunStage('Đã nhận kết quả')
    else if (event === 'change_set.ready') setRunStage('Chờ bạn xác nhận')
    else if (event === 'run.heartbeat') setRunStage('Đang khởi tạo run')
  }

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
    queryKey: conversationId ? ['mimi', 'conversation', conversationId] : ['mimi', 'current'],
    queryFn: () => conversationId ? fetchMimiConversation(conversationId) : fetchCurrentMimiConversation(),
    ...NO_POLLING_QUERY_OPTIONS,
  })
  const queryKey = conversationId ? ['mimi', 'conversation', conversationId] : ['mimi', 'current']

  const createConversation = useMutation({
    mutationFn: () => createMimiConversation(),
    onSuccess: (created) => {
      onConversationCreated?.(created.id)
      void queryClient.invalidateQueries({ queryKey: ['mimi'] })
    },
  })

  const send = useMutation({
    mutationFn: ({ current, content, clientId, revision }: {
      current: MimiConversation
      content: string
      clientId: string
      revision?: { id: string; digest: string } | null
    }) => streamMimiMessage(
      current.id,
      content,
      current.generation,
      clientId,
      revision ?? null,
      handleStreamEvent,
    ),
    onMutate: () => {
      setRunStartedAt(Date.now())
      setRunStage('Đang gửi yêu cầu')
      setStreamedText('')
    },
    onSuccess: (data) => {
      queryClient.setQueryData(queryKey, data)
      setDraft('')
      setRunStage(data.runs.at(-1)?.state === 'waiting_confirmation' ? 'Chờ bạn xác nhận' : 'Đã hoàn tất')
      setActiveRunId(null)
      setStreamedText('')
      void queryClient.invalidateQueries({ queryKey: ['mimi', 'conversations'] })
    },
    onError: () => setRunStage('Mất kết nối quan sát · run có thể vẫn tiếp tục'),
  })

  const cancel = useMutation({
    mutationFn: (runId: string) => cancelMimiRun(runId),
    onSuccess: () => setRunStage('Đang huỷ theo yêu cầu'),
  })

  const resume = useMutation({
    mutationFn: (runId: string) => resumeMimiRun(runId, handleStreamEvent),
    onMutate: () => {
      setRunStartedAt(Date.now())
      setRunStage('Đang tiếp tục từ checkpoint')
      setStreamedText('')
    },
    onSuccess: (data) => {
      queryClient.setQueryData(queryKey, data)
      setActiveRunId(null)
      setStreamedText('')
      setRunStage(data.runs.at(-1)?.state === 'waiting_confirmation' ? 'Chờ bạn xác nhận' : 'Đã hoàn tất')
    },
    onError: () => setRunStage('Không thể Resume; checkpoint vẫn được giữ nguyên'),
  })

  const reconcile = useMutation({
    mutationFn: (runId: string) => reconcileMimiRun(runId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey }),
  })

  const decision = useMutation({
    mutationFn: ({ changeSet, choice, key }: {
      changeSet: MimiChangeSet
      choice: 'confirm' | 'reject'
      key: string
    }) => decideMimiChangeSet(changeSet, choice, key),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey }),
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
      void queryClient.invalidateQueries({ queryKey })
    },
  })

  const current = conversation.data
  const pendingChangeSet = useMemo(
    () => [...(current?.change_sets ?? [])].reverse().find((item) => item.state === 'pending'),
    [current?.change_sets],
  )
  const latestReceipt = current?.receipts.at(-1)
  const latestRun = current?.runs.at(-1)
  const runPending = send.isPending || resume.isPending
  const elapsed = useElapsed(runStartedAt, runPending)

  function submitMessage(event: React.FormEvent) {
    event.preventDefault()
    if (!current || !draft.trim() || runPending || !online) return
    const revision = pendingChangeSet && requestsPreviewRevision(draft)
      ? { id: pendingChangeSet.id, digest: pendingChangeSet.digest }
      : null
    send.mutate({ current, content: draft, clientId: crypto.randomUUID(), revision })
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
          <MimiAvatar className="mx-auto" size="lg" state="idle" />
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
            {createConversation.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : <MimiAvatar size="xs" state="idle" />}
            Bắt đầu conversation STANDARD
          </Button>
        </CardContent>
      </Card>
    )
  }

  const mimiState: MimiState = runPending
    ? (runStage.includes('thực thi') || runStage.includes('áp dụng') ? 'executing' : 'thinking')
    : (latestRun?.state === 'waiting_confirmation' ? 'ready' : 'idle')

  return (
    <section className="min-w-0 space-y-4" aria-labelledby={`mimi-title-${variant}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <MimiAvatar size="md" state={mimiState} showGlow={runPending} />
          <div>
            <h3 id={`mimi-title-${variant}`} className="text-lg font-extrabold text-primary">{current.title ?? 'Conversation hiện tại'}</h3>
            <p className="text-sm text-muted-foreground">STANDARD · {runPending ? runStage : 'sẵn sàng'}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={online ? 'secondary' : 'destructive'}>
            {online ? <Wifi aria-hidden="true" /> : <WifiOff aria-hidden="true" />}
            {online ? 'Thiết bị có mạng' : 'Thiết bị mất mạng'}
          </Badge>
          {latestRun ? <Badge variant="outline"><CircleDot aria-hidden="true" />{mimiRunLabel(latestRun.state)}</Badge> : null}
        </div>
      </div>

      {runPending ? (
        <div role="status" aria-atomic="true" className="rounded-lg bg-accent p-3 text-sm text-accent-foreground">
          <div className="flex items-center gap-2 font-semibold">
            <LoaderCircle className="size-5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            {runStage}
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs">
            <span className="font-mono tabular-nums">Đã chạy {elapsedLabel(elapsed)}</span>
            {activeRunId ? (
              <Button size="sm" variant="outline" disabled={cancel.isPending} onClick={() => cancel.mutate(activeRunId)}>
                {cancel.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : <Square />}
                Huỷ run
              </Button>
            ) : null}
          </div>
          <p className="mt-1 text-xs">Đóng side-chat hoặc chuyển tab không dừng run; mở lại conversation để xem trạng thái mới nhất.</p>
        </div>
      ) : null}

      {send.isError && activeRunId ? (
        <div role="alert" className="rounded-lg bg-warn-bg p-3 text-sm">
          <p className="font-semibold">Kênh quan sát đã ngắt; run không bị gửi lại.</p>
          <p className="mt-1 text-xs">Mở lại conversation để đọc event bền vững, hoặc huỷ run đang chạy.</p>
          <Button className="mt-2" size="sm" variant="outline" disabled={cancel.isPending} onClick={() => cancel.mutate(activeRunId)}>
            {cancel.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : <Square />}
            Huỷ run
          </Button>
        </div>
      ) : null}

      {latestRun && (
        ['retryable', 'deadline_exceeded', 'outcome_unknown'].includes(latestRun.state)
        || (latestRun.state === 'cancelled' && latestRun.provider_outcome === 'unknown')
      ) ? (
        <div className="rounded-lg border border-warn/40 bg-warn-bg p-3 text-sm">
          <p className="font-semibold">Run đã dừng tại checkpoint provider.</p>
          {latestRun.provider_outcome === 'unknown' ? (
            <div className="mt-1 space-y-2">
              <p className="text-xs">Kết quả provider chưa xác định nên Mimi không tự gửi lại. Reconcile trước khi quyết định bước tiếp.</p>
              <Button size="sm" variant="outline" disabled={reconcile.isPending} onClick={() => reconcile.mutate(latestRun.id)}>
                {reconcile.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : <RotateCcw />}
                Reconcile provider
              </Button>
              {reconcile.isError ? <p role="alert" className="text-xs text-bad">Chưa thể xác minh generation; Mimi vẫn giữ outcome unknown và không retry.</p> : null}
            </div>
          ) : (
            <Button className="mt-2" size="sm" variant="outline" disabled={resume.isPending} onClick={() => resume.mutate(latestRun.id)}>
              {resume.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : <RotateCcw />}
              Resume
            </Button>
          )}
        </div>
      ) : null}

      {!online ? (
        <p role="status" className="rounded-lg bg-warn-bg p-3 text-sm text-foreground">
          Bạn đang offline. Draft được giữ trên màn hình và chưa được lưu ở trình duyệt.
        </p>
      ) : null}

      <div className={variant === 'dock'
        ? 'max-h-[42dvh] min-h-56 space-y-3 overflow-y-auto rounded-xl bg-muted/50 p-3 xl:max-h-[calc(100vh-28rem)] xl:min-h-72'
        : 'max-h-[32rem] min-h-64 space-y-3 overflow-y-auto rounded-xl bg-muted/50 p-3'} data-testid="mimi-messages">
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
        {streamedText ? (
          <article aria-live="polite" className="mr-auto max-w-[88%] rounded-xl bg-card px-4 py-3 ring-1 ring-primary/20">
            <p className="whitespace-pre-wrap break-words text-sm">{streamedText}</p>
          </article>
        ) : null}
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
          disabled={runPending}
          onChange={(event) => setDraft(event.target.value)}
        />
        {send.isError ? <p role="alert" className="text-sm text-bad">{errorMessage(send.error)}</p> : null}
        <div className="flex items-center justify-between gap-3">
          <p aria-live="polite" className="text-xs text-muted-foreground">
            {runPending ? 'Mimi đang làm việc…' : 'Không có thay đổi nào được ghi khi chưa xác nhận.'}
          </p>
          <Button type="submit" className="min-h-11" disabled={!draft.trim() || runPending || !online}>
            {runPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : <Send />}
            Gửi
          </Button>
        </div>
      </form>

      {current.events.length ? (
        <details className="rounded-lg border p-3 text-sm">
          <summary className="cursor-pointer font-semibold">Chi tiết kỹ thuật ({current.events.length})</summary>
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
