import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, LoaderCircle, MessageSquareWarning, ReceiptText, RotateCcw, Send, Square, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { MimiAvatar, type MimiState } from '@/components/brand'
import { MimiConfiguration } from '@/MimiConfiguration'
import { MimiMessageText } from '@/MimiMessageText'
import { ApiError, TimeoutError } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import {
  createMimiConversation,
  cancelMimiRun,
  decideMimiChangeSet,
  fetchMimiCapabilities,
  fetchMimiConversation,
  fetchCurrentMimiConversation,
  observeMimiRun,
  pauseMimiRun,
  reconcileMimiRun,
  resumeMimiRun,
  saveMimiFeedback,
  streamMimiMessage,
  type MimiChangeSet,
  type MimiConversation,
} from '@/mimi-api'
import {
  mimiFeedbackTargets,
  mimiRunIsResumable,
  mimiTerminalRunStage,
  resolveCancelAcknowledgment,
  mimiTaskScheduleLabel,
  resolveMimiFeedbackTarget,
} from '@/mimi-presentation'
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
  onRevise,
}: {
  changeSet: MimiChangeSet
  pending: boolean
  error: string | null
  onDecision: (decision: 'confirm' | 'reject') => void
  onRevise: () => void
}) {
  const task = changeSet.operation.args
  return (
    <Card data-testid="mimi-change-set" className="border-primary/20 bg-primary/5">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <Badge>Chờ xác nhận</Badge>
          <Badge variant="outline">Task</Badge>
        </div>
        <CardTitle>Tạo Task “{task.title}”</CardTitle>
        <CardDescription>
          Kiểm tra toàn bộ nội dung dưới đây. Chỉ khi bạn xác nhận, công việc mới được thêm vào danh sách.
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
        </dl>
        <div className="space-y-2 rounded-lg bg-card p-3">
          <p className="text-sm"><span className="font-semibold">Ưu tiên: </span>{task.priority === 'p1' ? 'Cao' : task.priority === 'p2' ? 'Vừa' : task.priority === 'p3' ? 'Thấp' : 'Chưa chọn'}</p>
          <div><p className="text-sm font-semibold">Ghi chú</p>{task.body_md ? <MimiMessageText text={task.body_md} /> : <p className="text-sm text-muted-foreground">Không có ghi chú</p>}</div>
          {task.items.length ? <div><p className="text-sm font-semibold">Các việc nhỏ</p><ul className="mt-1 list-disc space-y-1 pl-5 text-sm">{task.items.map((item, index) => <li key={index}>{item}</li>)}</ul></div> : null}
        </div>
        <details className="rounded-lg border px-3 py-2 text-xs">
          <summary className="cursor-pointer font-semibold">Chi tiết kỹ thuật</summary>
          <dl className="mt-2 space-y-1">
            <div><dt className="font-semibold">Loại thay đổi</dt><dd>{changeSet.operation.tool}</dd></div>
            <div><dt className="font-semibold">Mã đối chiếu</dt><dd className="break-all font-mono">{changeSet.digest}</dd></div>
          </dl>
        </details>
        {error ? <p role="alert" className="text-sm text-bad">{error}</p> : null}
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button className="min-h-11" variant="secondary" disabled={pending} onClick={onRevise}>
            Sửa phương án này
          </Button>
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
  const [revisionTarget, setRevisionTarget] = useState<{ id: string; digest: string } | null>(null)
  const messageInputRef = useRef<HTMLTextAreaElement>(null)
  const [online, setOnline] = useState(() => navigator.onLine)
  const [feedbackDraft, setFeedbackDraft] = useState('')
  const [feedbackExpected, setFeedbackExpected] = useState('')
  const [feedbackClientId, setFeedbackClientId] = useState<string | null>(null)
  const [feedbackTargetKey, setFeedbackTargetKey] = useState('')
  const [feedbackBinding, setFeedbackBinding] = useState<{
    conversationId: string
    targetKey: string
  } | null>(null)
  const [feedbackAcknowledgment, setFeedbackAcknowledgment] = useState<{
    conversationId: string
    targetKey: string
  } | null>(null)
  const [feedbackNotice, setFeedbackNotice] = useState<string | null>(null)
  const feedbackDraftRevision = useRef(0)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [runStartedAt, setRunStartedAt] = useState<number | null>(null)
  const [runStage, setRunStage] = useState('Sẵn sàng')
  const [cancelRequestedRunId, setCancelRequestedRunId] = useState<string | null>(null)
  const [streamedText, setStreamedText] = useState('')
  const runStageRunId = useRef<string | null>(null)
  const previousRunConversation = useRef<string | null>(null)

  const handleStreamEvent = useCallback(({ event, data }: { event: string; data: Record<string, unknown> }) => {
    if (event === 'run.reserved' && typeof data.run_id === 'string') {
      if (runStageRunId.current && runStageRunId.current !== data.run_id) return
      runStageRunId.current = data.run_id
      setCancelRequestedRunId(null)
      setActiveRunId(data.run_id)
      setRunStage('Đã nhận yêu cầu')
    } else if (
      typeof data.run_id === 'string'
      && runStageRunId.current !== data.run_id
    ) return
    else if (event === 'context.tasks_read') setRunStage('Đã đọc Task STANDARD')
    else if (event === 'context.manifest') setRunStage('Đã chuẩn bị ngữ cảnh')
    else if (event === 'context.checkpoint.activated') setRunStage('Đã thu gọn ngữ cảnh')
    else if (event === 'agent.awaiting_model') setRunStage('Mimi đang suy luận')
    else if (event === 'agent.executing_read_tools') setRunStage('Mimi đang đọc dữ liệu')
    else if (event === 'draft.ready') setRunStage('Phương án đã sẵn sàng')
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
  }, [])

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
  const current = conversation.data
  const capabilities = useQuery({
    queryKey: ['mimi', 'capabilities'],
    queryFn: fetchMimiCapabilities,
    ...NO_POLLING_QUERY_OPTIONS,
  })

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
      startedAt: number
    }) => streamMimiMessage(
      current.id,
      content,
      current.generation,
      clientId,
      revision ?? null,
      handleStreamEvent,
    ),
    onMutate: ({ startedAt }) => {
      runStageRunId.current = null
      setActiveRunId(null)
      setCancelRequestedRunId(null)
      setRunStartedAt(startedAt)
      setRunStage('Đang gửi yêu cầu')
      setStreamedText('')
    },
    onSuccess: (data, variables) => {
      queryClient.setQueryData(queryKey, data)
      setDraft('')
      if (variables.revision) setRevisionTarget(null)
      const terminalRun = data.runs.at(-1)
      if (terminalRun && runStageRunId.current === terminalRun.id) {
        runStageRunId.current = null
        setRunStage(mimiTerminalRunStage(terminalRun.state, terminalRun.provider_outcome))
        setActiveRunId((active) => active === terminalRun.id ? null : active)
        setCancelRequestedRunId((pending) => pending === terminalRun.id ? null : pending)
        setStreamedText('')
      }
      void queryClient.invalidateQueries({ queryKey: ['mimi', 'conversations'] })
    },
    onError: () => setRunStage('Mất kết nối quan sát · run có thể vẫn tiếp tục'),
  })

  const resume = useMutation({
    mutationFn: ({ runId }: { runId: string; startedAt: number }) => resumeMimiRun(runId, handleStreamEvent),
    onMutate: ({ startedAt }) => {
      runStageRunId.current = null
      setActiveRunId(null)
      setCancelRequestedRunId(null)
      setRunStartedAt(startedAt)
      setRunStage('Đang tiếp tục từ checkpoint')
      setStreamedText('')
    },
    onSuccess: (data) => {
      queryClient.setQueryData(queryKey, data)
      const terminalRun = data.runs.at(-1)
      if (terminalRun && runStageRunId.current === terminalRun.id) {
        const completedRunId = terminalRun.id
        runStageRunId.current = null
        setActiveRunId((active) => active === completedRunId ? null : active)
        setStreamedText('')
        setRunStage(mimiTerminalRunStage(terminalRun.state, terminalRun.provider_outcome))
        setCancelRequestedRunId((pending) => pending === completedRunId ? null : pending)
      }
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
    // Expiry/conflict may durably change the server artifact before returning
    // 409; refresh it so an obsolete pending card does not trap the user.
    onError: () => void queryClient.invalidateQueries({ queryKey }),
  })

  const feedback = useMutation({
    mutationFn: ({ current, target, comment, expected, clientId }: {
      current: MimiConversation
      target: { target_type: 'turn' | 'run' | 'call' | 'operation' | 'receipt'; target_id: string }
      comment: string
      expected: string
      clientId: string
      draftRevision: number
    }) => saveMimiFeedback(current.id, target, comment, expected, clientId),
    onSuccess: (_saved, variables) => {
      const targetKey = `${variables.target.target_type}:${variables.target.target_id}`
      setFeedbackAcknowledgment({ conversationId: variables.current.id, targetKey })
      if (current?.id === variables.current.id && feedbackDraftRevision.current === variables.draftRevision) {
        setFeedbackDraft('')
        setFeedbackExpected('')
        setFeedbackClientId(null)
        setFeedbackBinding(null)
        feedbackDraftRevision.current += 1
      }
      void queryClient.invalidateQueries({ queryKey: ['mimi'] })
    },
  })

  const pendingChangeSet = useMemo(
    () => [...(current?.change_sets ?? [])].reverse().find((item) => item.state === 'pending'),
    [current?.change_sets],
  )
  const activeRevision = revisionTarget
    && pendingChangeSet?.id === revisionTarget.id
    && pendingChangeSet.digest === revisionTarget.digest
    ? revisionTarget
    : null
  const latestReceipt = current?.receipts.at(-1)
  const latestRun = current?.runs.at(-1)
  const latestRunCanResume = latestRun ? mimiRunIsResumable(latestRun) : false
  const cancel = useMutation({
    mutationFn: (runId: string) => cancelMimiRun(runId),
    onMutate: (runId) => {
      if (runStageRunId.current === null && latestRun?.id === runId) {
        runStageRunId.current = runId
      }
      setCancelRequestedRunId(runId)
      if (runStageRunId.current === runId) setRunStage('Đang gửi yêu cầu huỷ')
    },
    onSuccess: (acknowledgment, runId) => {
      void queryClient.invalidateQueries({ queryKey })
      void queryClient.invalidateQueries({ queryKey: ['mimi', 'conversations'] })
      if (acknowledgment.run_id !== runId) return

      const latestRunNow = queryClient.getQueryData<MimiConversation>(queryKey)?.runs.at(-1) ?? latestRun
      const update = resolveCancelAcknowledgment(
        runId,
        runStageRunId.current,
        latestRunNow
          ? {
            id: latestRunNow.id,
            state: latestRunNow.state,
            provider_outcome: latestRunNow.provider_outcome,
          }
          : null,
        acknowledgment.state,
      )
      if (update.clearActiveRun) {
        setActiveRunId((active) => active === runId ? null : active)
      }
      if (update.stage && (
        runStageRunId.current === runId
        || (runStageRunId.current === null && latestRunNow?.id === runId)
      )) {
        setRunStage(update.stage)
      }
      if (update.apply && acknowledgment.state === 'cancelling') {
        setCancelRequestedRunId(runId)
      } else {
        setCancelRequestedRunId((pending) => pending === runId ? null : pending)
      }
      if (latestRunNow?.id === runId && update.needsReconcile) {
        runStageRunId.current = null
      }
    },
    onError: (_error, runId) => {
      setCancelRequestedRunId((pending) => pending === runId ? null : pending)
      if (runStageRunId.current === runId) setRunStage('Chưa gửi được yêu cầu huỷ')
    },
  })
  const pause = useMutation({
    mutationFn: (runId: string) => pauseMimiRun(runId),
    onSuccess: (acknowledgment, runId) => {
      void queryClient.invalidateQueries({ queryKey })
      void queryClient.invalidateQueries({ queryKey: ['mimi', 'conversations'] })
      if (acknowledgment.run_id !== runId || acknowledgment.pause_requested !== true) return
    },
  })
  const feedbackTargets = current ? mimiFeedbackTargets(current) : []
  const hasFeedbackDraft = !!feedbackDraft.trim() || !!feedbackExpected.trim()
  const feedbackNoticeText = hasFeedbackDraft
    && !!feedbackBinding
    && !!current
    && feedbackBinding.conversationId !== current.id
    ? 'Cuộc hội thoại đã đổi. Bản nháp được giữ nguyên; hãy chọn rõ mục mới để gắn lại.'
    : feedbackNotice
  const effectiveFeedbackTargetKey = feedbackTargetKey || (
    feedbackBinding && hasFeedbackDraft && feedbackBinding.conversationId === current?.id
      ? feedbackBinding.targetKey
      : ''
  )
  const selectedFeedbackTarget = current
    ? resolveMimiFeedbackTarget(
      feedbackTargets,
      effectiveFeedbackTargetKey,
      current.id,
      hasFeedbackDraft,
      feedbackBinding,
    )
    : null
  const resolvedFeedbackTargetKey = selectedFeedbackTarget
    ? `${selectedFeedbackTarget.target_type}:${selectedFeedbackTarget.target_id}`
    : ''
  const runPending = send.isPending || resume.isPending
  const durableRunActive = !!latestRun && ['accepted', 'building', 'running', 'executing'].includes(latestRun.state)
  const runtimeActive = runPending || durableRunActive
  const cancelRunId = durableRunActive
    ? latestRun?.id ?? null
    : runPending ? activeRunId : null
  const elapsed = useElapsed(runStartedAt ?? (latestRun ? new Date(latestRun.created_at).getTime() : null), runtimeActive)
  const observedRunId = latestRun?.id
  const observedRunState = latestRun?.state

  useEffect(() => {
    if (!current || previousRunConversation.current === current.id) return
    previousRunConversation.current = current.id
    runStageRunId.current = null
    setActiveRunId(null)
    setCancelRequestedRunId(null)
    setRevisionTarget(null)
    setRunStage('Sẵn sàng')
  }, [current])

  useEffect(() => {
    if (latestRun && durableRunActive && runStageRunId.current === null) {
      runStageRunId.current = latestRun.id
    }
  }, [latestRun, durableRunActive])

  useEffect(() => {
    if (!observedRunId || runPending) return
    if (!['accepted', 'building', 'running', 'executing'].includes(observedRunState ?? '')) return
    const controller = new AbortController()
    let replayStarted = false
    void observeMimiRun(observedRunId, (envelope) => {
      // Observation replays from sequence zero. Clear partial text from the
      // previous connection before appending canonical replay events.
      if (!replayStarted) {
        replayStarted = true
        setStreamedText('')
      }
      handleStreamEvent(envelope)
    }, controller.signal)
      .then((snapshot) => {
        if (controller.signal.aborted) return
        queryClient.setQueryData(
          conversationId ? ['mimi', 'conversation', conversationId] : ['mimi', 'current'],
          snapshot,
        )
        const observedRun = snapshot.runs.find((run) => run.id === observedRunId)
        if (observedRun && runStageRunId.current === observedRunId) {
          runStageRunId.current = null
          setActiveRunId((active) => active === observedRunId ? null : active)
          setCancelRequestedRunId((pending) => pending === observedRunId ? null : pending)
          setStreamedText('')
          const terminalStates = [
            'waiting_confirmation', 'completed', 'halted', 'cancelled', 'retryable',
            'outcome_unknown', 'deadline_exceeded', 'budget_exceeded',
          ]
          setRunStage(terminalStates.includes(observedRun.state)
            ? mimiTerminalRunStage(observedRun.state, observedRun.provider_outcome)
            : 'Đã đồng bộ với server')
        }
      })
      .catch(() => {
        if (controller.signal.aborted) return
        setRunStage('Mất kết nối quan sát · run có thể vẫn tiếp tục')
      })
    return () => controller.abort()
  }, [conversationId, handleStreamEvent, observedRunId, observedRunState, queryClient, runPending])

  function submitMessage(event?: React.SyntheticEvent) {
    event?.preventDefault()
    if (!current || !draft.trim() || runtimeActive || !online || (revisionTarget && !activeRevision)) return
    send.mutate({ current, content: draft, clientId: crypto.randomUUID(), revision: activeRevision, startedAt: Date.now() })
  }

  function startPreviewRevision(changeSet: MimiChangeSet) {
    setRevisionTarget({ id: changeSet.id, digest: changeSet.digest })
    requestAnimationFrame(() => messageInputRef.current?.focus())
  }

  function submitFeedback(event: React.FormEvent) {
    event.preventDefault()
    if (!current || !selectedFeedbackTarget || !feedbackDraft.trim() || feedback.isPending) return
    const clientId = feedbackClientId ?? crypto.randomUUID()
    setFeedbackClientId(clientId)
    feedback.mutate({
      current,
      target: selectedFeedbackTarget,
      comment: feedbackDraft,
      expected: feedbackExpected,
      clientId,
      draftRevision: feedbackDraftRevision.current,
    })
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
          <CardTitle>Bắt đầu trò chuyện với Mimi</CardTitle>
          <CardDescription>
            Bạn có thể hỏi Mimi hoặc nhờ đọc Task STANDARD. Với yêu cầu tạo Task được hỗ trợ, Mimi sẽ đưa phương án để bạn xem và xác nhận; thao tác khác tùy khả năng đang bật.
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
            Bắt đầu trò chuyện
          </Button>
        </CardContent>
      </Card>
    )
  }

  const mimiState: MimiState = runtimeActive
    ? (runStage.includes('thực thi') || runStage.includes('áp dụng') ? 'executing' : 'thinking')
    : (latestRun?.state === 'waiting_confirmation' ? 'ready' : 'idle')

  return (
    <section className="w-full max-w-full min-w-0 flex flex-col h-full space-y-4" aria-labelledby={`mimi-title-${variant}`}>
      <div className="flex items-center justify-between gap-2 border-b pb-2 shrink-0">
        <div className="flex flex-1 items-center gap-2 min-w-0">
          <MimiAvatar size="xs" state={mimiState} showGlow={runtimeActive} />
          <h3 id={`mimi-title-${variant}`} className="text-sm font-bold text-foreground truncate">
            {current.title ?? 'Conversation hiện tại'}
          </h3>
          <span className="text-[11px] text-muted-foreground shrink-0">· STANDARD</span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {!online ? <Badge variant="destructive" className="text-[10px] h-5">Mất mạng</Badge> : null}
          {latestRun?.state === 'waiting_confirmation' ? (
            <Badge variant="outline" className="text-[10px] h-5 border-amber-500/50 text-amber-600 bg-amber-50/50">
              Chờ xác nhận
            </Badge>
          ) : null}
        </div>
      </div>

      <MimiConfiguration conversationId={current.id} capabilities={capabilities.data} runtimeActive={runtimeActive} />

      {runtimeActive ? (
        <div role="status" aria-atomic="true" className="rounded-lg bg-accent p-3 text-sm text-accent-foreground">
          <div className="flex items-center gap-2 font-semibold">
            <LoaderCircle className="size-5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            {runStage === 'Sẵn sàng' && durableRunActive ? 'Mimi đang làm việc trên server' : runStage}
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs">
            <span className="font-mono tabular-nums">Đã chạy {elapsedLabel(elapsed)}</span>
            {cancelRunId && cancelRequestedRunId === cancelRunId ? (
              <span className="text-xs" role="status">
                {cancel.isPending ? 'Đang gửi yêu cầu huỷ…' : 'Đã gửi yêu cầu, đang chờ trạng thái mới…'}
              </span>
            ) : cancelRunId ? (
              <Button size="lg" variant="outline" disabled={cancel.isPending || pause.isPending} onClick={() => cancel.mutate(cancelRunId)}>
                {cancel.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : <Square />}
                Huỷ run ngay
              </Button>
            ) : null}
            {cancelRunId ? (
              pause.data?.run_id === cancelRunId && pause.data.pause_requested ? (
                <span className="text-xs" role="status" data-testid="mimi-pause-acknowledgment">
                  Đã nhận yêu cầu tạm dừng. Mimi sẽ chờ xong bước model/tool hiện tại; run chưa dừng.
                </span>
              ) : (
                <Button size="lg" variant="outline" disabled={pause.isPending || cancel.isPending} onClick={() => pause.mutate(cancelRunId)}>
                  {pause.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : null}
                  {pause.isPending ? 'Đang gửi yêu cầu…' : 'Tạm dừng sau bước này'}
                </Button>
              )
            ) : null}
          </div>
          <p className="mt-1 text-xs">Tạm dừng chờ xong bước hiện tại. Huỷ run gửi lệnh dừng ngay; model call đã bắt đầu có thể vẫn trả về. Đóng side-chat hoặc chuyển tab không dừng run.</p>
        </div>
      ) : null}

      {pause.isError ? <p role="alert" className="rounded-lg bg-warn-bg p-3 text-sm">Chưa gửi được yêu cầu tạm dừng. Run vẫn đang chạy; thử lại hoặc huỷ run ngay.</p> : null}

      {send.isError && cancelRunId ? (
        <div role="alert" className="rounded-lg bg-warn-bg p-3 text-sm">
          <p className="font-semibold">Kênh quan sát đã ngắt; run không bị gửi lại.</p>
          <p className="mt-1 text-xs">Mở lại conversation để đọc event bền vững, hoặc huỷ run đang chạy.</p>
          <Button className="mt-2" size="sm" variant="outline" disabled={cancel.isPending} onClick={() => cancel.mutate(cancelRunId)}>
            {cancel.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : <Square />}
            Huỷ run
          </Button>
        </div>
      ) : null}

      {latestRun && (
        latestRunCanResume
        || ['retryable', 'deadline_exceeded', 'outcome_unknown'].includes(latestRun.state)
        || (latestRun.state === 'cancelled' && latestRun.provider_outcome === 'unknown')
      ) ? (
        <div className="rounded-lg border border-warn/40 bg-warn-bg p-3 text-sm">
          <p className="font-semibold">{latestRunCanResume ? 'Run có thể tiếp tục theo trạng thái server.' : 'Run đã dừng tại checkpoint provider.'}</p>
          {latestRunCanResume ? (
            <div className="mt-1 space-y-2">
              <p className="text-xs">Tiếp tục sẽ tạo lượt chạy mới. Nếu server đã nhận kết quả model hợp lệ, Mimi sẽ dùng lại; nếu chưa, lượt mới có thể gọi model. Thay đổi dữ liệu vẫn cần xác nhận preview mới.</p>
              <Button size="lg" variant="outline" disabled={resume.isPending} onClick={() => resume.mutate({ runId: latestRun.id, startedAt: Date.now() })}>
                {resume.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : <RotateCcw />}
                Tiếp tục
              </Button>
            </div>
          ) : latestRun.provider_outcome === 'unknown' ? (
            <div className="mt-1 space-y-2">
              <p className="text-xs">Kết quả provider chưa xác định nên Mimi không tự gửi lại. Reconcile trước khi quyết định bước tiếp.</p>
              <Button size="sm" variant="outline" disabled={reconcile.isPending} onClick={() => reconcile.mutate(latestRun.id)}>
                {reconcile.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : <RotateCcw />}
                Reconcile provider
              </Button>
              {reconcile.isError ? <p role="alert" className="text-xs text-bad">Chưa thể xác minh generation; Mimi vẫn giữ outcome unknown và không retry.</p> : null}
            </div>
          ) : (
            <p className="mt-1 text-xs">Server chưa cho phép tiếp tục run này.</p>
          )}
        </div>
      ) : null}

      {!online ? (
        <p role="status" className="rounded-lg bg-warn-bg p-3 text-sm text-foreground">
          Bạn đang offline. Draft được giữ trên màn hình và chưa được lưu ở trình duyệt.
        </p>
      ) : null}

      <div className={variant === 'dock'
        ? 'max-h-[calc(100vh-18rem)] min-h-72 space-y-3 overflow-y-auto rounded-xl bg-muted/40 p-3'
        : 'flex-1 min-h-[22rem] space-y-3 overflow-y-auto rounded-xl bg-muted/30 p-4'} data-testid="mimi-messages">
        {current.messages.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Bạn có thể hỏi điều cần biết, nhờ Mimi đọc Task, hoặc cùng bàn một phương án. Mimi sẽ hỏi thêm khi còn thiếu thông tin.</p>
        ) : current.messages.map((message) => (
          <article
            key={message.id}
            className={message.role === 'user'
              ? 'ml-auto w-fit max-w-[min(88%,65ch)] rounded-xl bg-primary px-4 py-3 text-primary-foreground'
              : 'mr-auto w-fit max-w-[min(88%,65ch)] rounded-xl bg-card px-4 py-3 ring-1 ring-foreground/10'}
          >
            {message.role === 'user'
              ? <p className="whitespace-pre-wrap break-words text-sm">{message.content}</p>
              : <MimiMessageText text={message.content} />}
          </article>
        ))}
        {streamedText ? (
          <article aria-live="polite" className="mr-auto w-fit max-w-[min(88%,65ch)] rounded-xl bg-card px-4 py-3 ring-1 ring-primary/20">
            <MimiMessageText text={streamedText} />
          </article>
        ) : null}
      </div>

      {pendingChangeSet ? (
        <ChangeSetPreview
          changeSet={pendingChangeSet}
          pending={decision.isPending}
          error={decision.isError ? errorMessage(decision.error) : null}
          onRevise={() => startPreviewRevision(pendingChangeSet)}
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
            <CardDescription>Thao tác đã được lưu và có thể xem trong danh sách Task.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button variant="outline" onClick={onOpenTasks}>Mở Task</Button>
            <details className="rounded-lg border px-3 py-2 text-xs">
              <summary className="cursor-pointer font-semibold">Mã đối chiếu</summary>
              <p className="mt-2 break-all font-mono">{latestReceipt.id}</p>
            </details>
          </CardContent>
        </Card>
      ) : null}

      {feedbackTargets.length ? (
        <details className="rounded-xl border bg-card" data-testid="mimi-feedback">
          <summary className="cursor-pointer px-4 py-3 text-sm font-semibold">Gửi feedback (không bắt buộc)</summary>
          <Card className="border-0 shadow-none">
          <CardHeader>
            <CardTitle>Gửi feedback</CardTitle>
            <CardDescription>Feedback được gắn với đúng câu trả lời, run, lần gọi hoặc receipt bạn chọn.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-3" onSubmit={submitFeedback}>
              <div className="space-y-1.5">
                <label htmlFor="mimi-feedback-target" className="text-sm font-semibold">Mục cần góp ý</label>
                <Select
                  value={resolvedFeedbackTargetKey}
                  disabled={feedback.isPending}
                  onValueChange={(value) => {
                    const hadDraft = !!feedbackDraft.trim() || !!feedbackExpected.trim()
                    setFeedbackTargetKey(value)
                    setFeedbackClientId(null)
                    feedbackDraftRevision.current += 1
                    setFeedbackBinding(feedbackDraft.trim() || feedbackExpected.trim()
                      ? { conversationId: current.id, targetKey: value }
                      : null)
                    setFeedbackAcknowledgment(null)
                    setFeedbackNotice(hadDraft
                      ? 'Bản nháp hiện tại đã được gắn rõ với mục bạn vừa chọn.'
                      : null)
                    feedback.reset()
                  }}
                >
                  <SelectTrigger id="mimi-feedback-target" className="min-h-11 w-full bg-card">
                    <SelectValue placeholder="Chọn câu trả lời hoặc run" />
                  </SelectTrigger>
                  <SelectContent>
                    {feedbackTargets.map((target) => (
                      <SelectItem key={`${target.target_type}:${target.target_id}`} value={`${target.target_type}:${target.target_id}`}>
                        {target.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <label htmlFor="mimi-feedback" className="text-sm font-semibold">Điều gì cần sửa hoặc làm rõ?</label>
                <Textarea
                  id="mimi-feedback"
                  value={feedbackDraft}
                  maxLength={10_000}
                  aria-describedby="mimi-feedback-help"
                  disabled={feedback.isPending}
                  placeholder="Mô tả kết quả chưa đúng hoặc thiếu điều gì."
                  onChange={(event) => {
                    feedbackDraftRevision.current += 1
                    setFeedbackDraft(event.target.value)
                    setFeedbackClientId(null)
                    setFeedbackAcknowledgment(null)
                    if (!event.target.value.trim() && !feedbackExpected.trim()) setFeedbackNotice(null)
                    setFeedbackBinding(event.target.value.trim() && selectedFeedbackTarget
                      ? {
                        conversationId: current.id,
                        targetKey: `${selectedFeedbackTarget.target_type}:${selectedFeedbackTarget.target_id}`,
                      }
                      : event.target.value.trim() && feedbackBinding
                        ? feedbackBinding
                        : null)
                    feedback.reset()
                  }}
                />
                <p id="mimi-feedback-help" className="text-xs text-muted-foreground">Nội dung được mã hoá khi lưu.</p>
              </div>
              <div className="space-y-1.5">
                <label htmlFor="mimi-feedback-expected" className="text-sm font-semibold">Kết quả bạn mong đợi (không bắt buộc)</label>
                <Textarea
                  id="mimi-feedback-expected"
                  value={feedbackExpected}
                  maxLength={10_000}
                  disabled={feedback.isPending}
                  placeholder="Ví dụ: cần hỏi lại ngày trước khi tạo Task."
                  onChange={(event) => {
                    feedbackDraftRevision.current += 1
                    setFeedbackExpected(event.target.value)
                    setFeedbackClientId(null)
                    setFeedbackAcknowledgment(null)
                    if (!event.target.value.trim() && !feedbackDraft.trim()) setFeedbackNotice(null)
                    setFeedbackBinding(event.target.value.trim() && selectedFeedbackTarget
                      ? {
                        conversationId: current.id,
                        targetKey: `${selectedFeedbackTarget.target_type}:${selectedFeedbackTarget.target_id}`,
                      }
                      : event.target.value.trim() && feedbackBinding
                        ? feedbackBinding
                        : null)
                    feedback.reset()
                  }}
                />
              </div>
              {feedback.isError ? (
                <p role="alert" className="flex items-center gap-2 text-sm text-bad">
                  <MessageSquareWarning className="size-4" />
                  Chưa lưu feedback. {errorMessage(feedback.error)} Nội dung vẫn được giữ để thử lại.
                </p>
              ) : null}
              {(feedbackAcknowledgment?.conversationId === current.id
                && feedbackAcknowledgment.targetKey === resolvedFeedbackTargetKey
                && !!resolvedFeedbackTargetKey)
                || current.feedback.some((item) =>
                  item.target_type === selectedFeedbackTarget?.target_type
                  && item.target_id === selectedFeedbackTarget?.target_id,
                ) ? (
                <p role="status" className="text-sm text-ok">Feedback đã được xác nhận và gắn với mục đã chọn.</p>
              ) : null}
              {feedbackNoticeText ? (
                <p role="status" className="text-sm text-warn">{feedbackNoticeText}</p>
              ) : null}
              {hasFeedbackDraft && !selectedFeedbackTarget && !feedbackNoticeText ? (
                <p role="status" className="text-sm text-warn">
                  Bản nháp đang giữ liên kết cũ. Chọn rõ mục mới để gắn bản nháp trước khi lưu.
                </p>
              ) : null}
              {!feedback.isPending && current.feedback.some((item) =>
                item.target_type === selectedFeedbackTarget?.target_type
                && item.target_id === selectedFeedbackTarget?.target_id,
              ) ? (
                <p role="status" className="text-sm text-ok">Đã có feedback lưu cho mục này.</p>
              ) : null}
              <Button type="submit" variant="secondary" className="min-h-11" disabled={!selectedFeedbackTarget || !feedbackDraft.trim() || feedback.isPending}>
                {feedback.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : null}
                Lưu feedback
              </Button>
            </form>
          </CardContent>
          </Card>
        </details>
      ) : null}

      <form onSubmit={submitMessage} className="mt-2 shrink-0">
        {revisionTarget && !activeRevision ? (
          <div role="alert" className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-bad-bg p-3 text-sm text-bad">
            <p>Phương án đã đổi hoặc không còn chờ xác nhận. Tin nhắn chưa được gửi; hủy chế độ sửa hoặc chọn phương án đang chờ.</p>
            <Button type="button" size="lg" variant="outline" onClick={() => setRevisionTarget(null)}>Hủy sửa</Button>
          </div>
        ) : null}
        {activeRevision ? (
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-accent p-3 text-sm" role="status" data-testid="mimi-revision-target">
            <p>Đang sửa đúng phương án “{pendingChangeSet?.operation.args.title}”. Hãy mô tả nội dung cần thay đổi.</p>
            <Button type="button" size="lg" variant="outline" onClick={() => setRevisionTarget(null)}>Hủy sửa</Button>
          </div>
        ) : null}
        <div className="relative flex flex-col rounded-2xl border border-input bg-card shadow-xs focus-within:ring-2 focus-within:ring-ring focus-within:border-primary transition-all p-2.5">
          <Textarea
            id="mimi-message"
            ref={messageInputRef}
            data-testid="mimi-input"
            aria-label="Nhắn Mimi"
            value={draft}
            maxLength={12_000}
            placeholder={activeRevision
              ? 'Mô tả cách bạn muốn sửa phương án…'
              : 'Nhắn Mimi… (Nhấn Enter để gửi, Shift+Enter để xuống dòng)'}
            disabled={runtimeActive}
            className="min-h-12 w-full resize-none border-none bg-transparent p-1 text-sm shadow-none focus-visible:ring-0 focus-visible:outline-none"
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && event.altKey) {
                if ((event.nativeEvent as KeyboardEvent).isComposing) return
                event.preventDefault()
                const input = event.currentTarget
                const caret = input.selectionStart
                setDraft(input.value.slice(0, caret) + '\n' + input.value.slice(input.selectionEnd))
                requestAnimationFrame(() => input.setSelectionRange(caret + 1, caret + 1))
                return
              }
              if (event.key === 'Enter' && !event.shiftKey && !event.altKey) {
                if ((event.nativeEvent as KeyboardEvent).isComposing) return
                event.preventDefault()
                submitMessage(event)
              }
            }}
          />
          <div className="mt-1 flex items-center justify-between pt-1 text-xs text-muted-foreground border-t border-muted/50">
            <span aria-live="polite" className="truncate pr-2">
              {runtimeActive ? 'Mimi đang làm việc…' : 'Chưa xác nhận thì chưa ghi thay đổi.'}
            </span>
            <Button
              type="submit"
              size="sm"
              className="h-8 gap-1.5 rounded-xl px-3 font-semibold shrink-0"
              disabled={!draft.trim() || runtimeActive || !online || (revisionTarget !== null && !activeRevision)}
            >
              {runtimeActive ? <LoaderCircle className="size-3.5 animate-spin motion-reduce:animate-none" /> : <Send className="size-3.5" />}
              <span>Gửi</span>
            </Button>
          </div>
        </div>
        {send.isError ? <p role="alert" className="mt-1 text-xs text-bad">{errorMessage(send.error)}</p> : null}
      </form>

      {variant === 'dock' && current.events.length ? (
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
