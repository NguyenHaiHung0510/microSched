import { toast } from 'sonner'
import { feedbackComment } from '@/mimi-owner-feedback'
import { MimiBackdrop } from '@/MimiBackdrop'
import { MimiCollectionReview } from '@/MimiCollectionReview'
import { MimiFeedbackEvidence } from '@/MimiFeedbackEvidence'
import { mimiChangeTitle } from '@/mimi-collection'
import { clearMimiIntent, publishAuthoritativeMimiRefusal, readMimiIntent, saveMimiIntent, type MimiDecisionIntent } from '@/mimi-recovery'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { usePreviewExpired } from './mimi-preview-expiry'
import { MimiRunObservations } from '@/MimiRunObservations'
import { MimiCheckpointViewer } from './MimiCheckpointViewer'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, Check, Copy, ChevronDown, LoaderCircle, MessageSquareWarning, RotateCcw, Send, Sparkles, Square, X, ThumbsUp, ThumbsDown } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { MimiAvatar, type MimiState } from '@/components/brand'
import { MimiConfiguration } from '@/MimiConfiguration'
import { MimiMessageText } from '@/MimiMessageText'
import { MimiSystemNotice } from '@/MimiSystemNotice'
import { isVerifiedServerNotice } from '@/mimi-message-provenance'
import { ApiError, TimeoutError } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import {
  recoverMimiReceipt,
  prepareMimiUndo,
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
import { selectCreatedMimiConversation, setMimiComposerDraft, useMimiComposerDraft } from '@/mimi-selection'

function errorMessage(error: unknown): string {
  if (error instanceof TimeoutError) return error.message
  if (error instanceof ApiError) {
    if (error.status === 503 && error.message === 'mimi_busy_try_later') return 'Mimi đang bận. Nội dung bạn nhập vẫn được giữ; thử lại sau. Task vẫn dùng bình thường.'
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


export function ChangeSetPreview({
  changeSet,
  pending,
  error,
  onDecision,
  onRevise,
  conversationId = '',
}: {
  changeSet: MimiChangeSet
  conversationId?: string
  pending: boolean
  error: string | null
  onDecision: (decision: 'confirm' | 'reject') => void
  onRevise: () => void
}) {
  const expired = usePreviewExpired(changeSet.expires_at)
  if (changeSet.operation.tool === 'task.collection.v1') return <MimiCollectionReview changeSet={changeSet} plan={changeSet.operation.args} conversationId={conversationId} pending={pending} error={error} onDecision={onDecision} onRevise={onRevise} />
  const task = changeSet.operation.args
  return (
    <Card data-testid="mimi-change-set" className="border-primary/20 bg-primary/5">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <Badge role="status" aria-live="polite">{expired ? 'Preview đã hết hạn' : 'Chờ xác nhận'}</Badge>
          <Badge variant="outline">Task</Badge>
        </div>
        <CardTitle>Tạo Task “{task.title}”</CardTitle>
        <CardDescription>
          {expired
            ? 'Gửi yêu cầu mới trong ô chat để Mimi tạo preview khác. Phương án này không còn dùng để ghi thay đổi.'
            : 'Kiểm tra toàn bộ nội dung dưới đây. Chỉ khi bạn xác nhận, công việc mới được thêm vào danh sách.'}
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
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap" data-testid="mimi-preview-actions">
          <Button className="min-h-11" variant="secondary" disabled={pending || expired} onClick={onRevise}>
            Sửa phương án này
          </Button>
          <Button
            className="min-h-11"
            disabled={pending || expired}
            onClick={() => onDecision('confirm')}
          >
            {pending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : <Check />}
            Xác nhận tạo Task
          </Button>
          <Button
            className="min-h-11"
            variant="outline"
            disabled={pending || expired}
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
  settingsOpen,
  onSettingsOpenChange,
  technicalOpen,
  onTechnicalOpenChange,
  onTechnicalCloseFocus,
  onOpenConfiguration,
}: {
  onOpenTasks: () => void
  variant?: 'workspace' | 'dock'
  conversationId?: string | null
  settingsOpen?: boolean
  onSettingsOpenChange?: (open: boolean) => void
  onOpenConfiguration?: () => void
  technicalOpen?: boolean
  onTechnicalOpenChange?: (open: boolean) => void
  onTechnicalCloseFocus?: () => void
  onConversationCreated?: (conversationId: string) => void
}) {
  const queryClient = useQueryClient()
  const [revisionTarget, setRevisionTarget] = useState<{ id: string; digest: string } | null>(null)
  const messageInputRef = useRef<HTMLTextAreaElement>(null)
  const [online, setOnline] = useState(() => navigator.onLine)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const [feedbackMood, setFeedbackMood] = useState<'positive' | 'negative'>('negative')
  const [feedbackReasons, setFeedbackReasons] = useState<string[]>([])
  const [localDecisionIntent, setDecisionIntent] = useState<MimiDecisionIntent | null>(null)
  const [recoveryNotice, setRecoveryNotice] = useState<string | null>(null)
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
    mood: 'positive' | 'negative'
  } | null>(null)
  const [feedbackNotice, setFeedbackNotice] = useState<string | null>(null)
  const feedbackDraftRevision = useRef(0)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [runStartedAt, setRunStartedAt] = useState<number | null>(null)
  const [runStage, setRunStage] = useState('Sẵn sàng')
  const [cancelRequestedRunId, setCancelRequestedRunId] = useState<string | null>(null)
  const [streamedText, setStreamedText] = useState('')
  const transcriptRef = useRef<HTMLDivElement | null>(null)
  const followLatest = useRef(true)
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
    else if (event === 'context.tasks_read') setRunStage('Đang chuẩn bị ngữ cảnh')
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
    else if (event === 'run.heartbeat') { /* Observation heartbeat carries no new product phase. */ }
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
  const decisionIntent = current ? (localDecisionIntent?.conversationId === current.id ? localDecisionIntent : readMimiIntent(current.id, current.change_sets)) : null
  const [draft, setDraft] = useMimiComposerDraft(current?.id)
  useEffect(() => {
    const input = messageInputRef.current
    if (!input || CSS.supports('field-sizing', 'content')) return
    const scrollTop = input.scrollTop
    input.style.height = 'auto'
    input.style.height = `${Math.min(160, Math.max(36, input.scrollHeight))}px`
    input.scrollTop = scrollTop
  }, [draft])
  useEffect(() => {
    if (!followLatest.current || !current?.messages.length) return
    const frame = requestAnimationFrame(() => transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: 'auto' }))
    return () => cancelAnimationFrame(frame)
  }, [current?.messages.length, streamedText])
  const capabilities = useQuery({
    queryKey: ['mimi', 'capabilities'],
    queryFn: fetchMimiCapabilities,
    ...NO_POLLING_QUERY_OPTIONS,
  })

  const createConversation = useMutation({
    mutationFn: () => createMimiConversation(),
    onSuccess: (created) => {
      selectCreatedMimiConversation(queryClient, created)
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
      followLatest.current = true
    },
    onSuccess: (data, variables) => {
      queryClient.setQueryData(queryKey, data)
      setMimiComposerDraft(variables.current.id, '')
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
    onError: (error) => setRunStage(error instanceof ApiError && error.status === 503
      ? 'Mimi đang bận · yêu cầu chưa được nhận'
      : 'Mất kết nối quan sát · run có thể vẫn tiếp tục'),
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
    mutationFn: (intent: MimiDecisionIntent) => decideMimiChangeSet(intent.changeSet, intent.choice, intent.key),
    onSuccess: (_saved, intent) => {
      clearMimiIntent(intent.conversationId)
      setDecisionIntent(null)
      setRecoveryNotice(null)
      void queryClient.invalidateQueries({ queryKey: ['mimi'] })
    },
    onError: async (error, intent) => {
      // A known frontier refusal still needs a matching authoritative snapshot.
      const detail = error instanceof ApiError && error.body && typeof error.body === 'object' && 'detail' in error.body ? error.body.detail : null
      if (intent.choice === 'confirm' && intent.changeSet.operation.tool === 'task.collection.v1' && error instanceof ApiError && error.status === 409 && ['change_set_frontier_stale', 'change_set_stale'].includes(String(detail))) {
        try {
          const snapshot = await fetchMimiConversation(intent.conversationId)
          if (await publishAuthoritativeMimiRefusal(queryClient, intent, snapshot)) {
            clearMimiIntent(intent.conversationId)
            setDecisionIntent(null)
            setRecoveryNotice('Server đã từ chối preview cũ; không áp dụng thay đổi. Hãy yêu cầu Mimi lập phương án mới.')
            void queryClient.invalidateQueries({ queryKey: ['mimi'] })
            return
          }
        } catch { /* Missing snapshot leaves the original intent UNKNOWN. */ }
      }
      setRecoveryNotice('Chưa biết kết quả ghi. Đã giữ đúng khóa lần xác nhận; không tự gửi lại. Đọc receipt để đối chiếu.')
      void queryClient.invalidateQueries({ queryKey })
    },
  })

  const recover = useMutation({
    mutationFn: async (intent: MimiDecisionIntent) => {
      if (intent.choice === 'confirm') {
        try { return await recoverMimiReceipt(intent.conversationId, intent.changeSet, intent.key) } catch (error) {
          if (!(error instanceof ApiError) || error.status !== 404) throw error
          const snapshot = await fetchMimiConversation(intent.conversationId)
          if (!await publishAuthoritativeMimiRefusal(queryClient, intent, snapshot)) throw error
          return null // Authoritative terminal refusal, not inferred from receipt absence.
        }
      }
      const snapshot = await fetchMimiConversation(intent.conversationId)
      if (snapshot.change_sets.find((c) => c.id === intent.changeSet.id)?.state !== 'rejected') throw new Error('Chưa xác định kết quả từ chối.')
      return null
    },
    onSuccess: (_receipt, intent) => {
      clearMimiIntent(intent.conversationId)
      setDecisionIntent(null)
      setRecoveryNotice(_receipt ? 'Đã đối chiếu receipt đã lưu; không gửi lại thao tác.' : 'Đã đọc trạng thái server: preview không được áp dụng và không còn chờ xác nhận. Cần phương án mới.')
      void queryClient.invalidateQueries({ queryKey: ['mimi'] })
    },
    onError: () => setRecoveryNotice('Chưa tìm thấy receipt khớp. Kết quả vẫn UNKNOWN; không tự gửi lại hoặc coi là chưa ghi.'),
  })
  const undo = useMutation({ mutationFn: prepareMimiUndo, onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['mimi'] }) })
  function confirmDecision(changeSet: MimiChangeSet, choice: 'confirm' | 'reject') {
    if (!current || decisionIntent || decision.isPending) return
    const intent = { conversationId: current.id, changeSet, choice, key: crypto.randomUUID() }
    try { saveMimiIntent(intent) } catch { setRecoveryNotice('Không giữ được khóa đối chiếu ở phiên trình duyệt. Chưa gửi thao tác.'); return }
    setDecisionIntent(intent)
    decision.mutate(intent)
  }

  const feedback = useMutation({
    mutationFn: ({ current, target, comment, expected, clientId }: {
      current: MimiConversation
      target: { target_type: 'turn' | 'run' | 'call' | 'operation' | 'receipt'; target_id: string }
      comment: string
      expected: string
      clientId: string
      draftRevision: number
      mood: 'positive' | 'negative'
    }) => saveMimiFeedback(current.id, target, comment, expected, clientId),
    onSuccess: (_saved, variables) => {
      const targetKey = `${variables.target.target_type}:${variables.target.target_id}`
      setFeedbackAcknowledgment({ conversationId: variables.current.id, targetKey, mood: variables.mood })
      if (variables.mood === 'positive') queryClient.setQueryData(['mimi', 'positive-feedback-intent', variables.current.id, variables.target.target_id], { clientId: variables.clientId, saved: true })
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
  const pendingPreviewExpired = usePreviewExpired(pendingChangeSet?.expires_at ?? '')
  const activeRevision = revisionTarget
    && pendingChangeSet?.id === revisionTarget.id
    && pendingChangeSet.digest === revisionTarget.digest
    ? revisionTarget
    : null
  const latestReceipt = current?.receipts.at(-1)
  const latestRun = current?.runs.at(-1)
  const latestRunExceedsContext = latestRun?.state === 'budget_exceeded' && [
    'mimi_compaction_fixed_or_single_source_exceeds_context',
    'mimi_history_message_exceeds_context_window',
    'mimi_compaction_fixed_current_input_exceeds_context',
  ].includes(latestRun.error_code ?? '')
  const latestContext = current?.events.filter((event) => event.kind === 'context.manifest' && event.run_id === latestRun?.id).at(-1)
  const latestCheckpoint = current?.events.filter((event) => event.kind === 'context.checkpoint.activated').at(-1)
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
    if (!current || decisionIntent || !draft.trim() || runtimeActive || !online || (revisionTarget && !activeRevision)) return
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
      comment: feedbackComment(feedbackMood, feedbackReasons, feedbackDraft),
      expected: feedbackExpected,
      mood: feedbackMood,
      clientId,
      draftRevision: feedbackDraftRevision.current,
    })
  }

  function toggleFeedbackReason(reason: string) {
    setFeedbackReasons((old) => old.includes(reason) ? old.filter((item) => item !== reason) : [...old, reason])
    if (feedbackMood === 'negative') {
      feedbackDraftRevision.current += 1
      setFeedbackClientId(null)
      setFeedbackAcknowledgment(null)
      feedback.reset()
    }
  }

  function openMessageFeedback(messageId: string, mood: 'positive' | 'negative') {
    if (!current || feedback.isPending) return
    const targetKey = `turn:${messageId}`
    setFeedbackMood(mood)
    setFeedbackReasons([])
    setFeedbackTargetKey(targetKey)
    setFeedbackOpen(true)
    setFeedbackBinding({ conversationId: current.id, targetKey })
    setFeedbackAcknowledgment(null)
    setFeedbackNotice(null)
    feedback.reset()
    feedbackDraftRevision.current += 1
    if (mood === 'negative') { setFeedbackClientId(null); return }
    const intentKey = ['mimi', 'positive-feedback-intent', current.id, messageId]
    const intent = queryClient.getQueryData<{ clientId: string; saved: boolean }>(intentKey)
    const clientId = intent?.clientId ?? `mimi-positive:${current.id}:${messageId}`
    queryClient.setQueryData(intentKey, { clientId, saved: intent?.saved ?? false })
    setFeedbackClientId(clientId)
    if (intent?.saved) { setFeedbackAcknowledgment({ conversationId: current.id, targetKey, mood }); return }
    feedback.mutate({ current, target: { target_type: 'turn', target_id: messageId }, comment: feedbackComment('positive', [], ''), expected: '', clientId, draftRevision: -1, mood })
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
    ? (runStage.includes('thực thi') || runStage.includes('áp dụng') || runStage.includes('đọc dữ liệu') ? 'executing' : 'thinking')
    : (latestRun?.state === 'waiting_confirmation' ? 'ready' : 'idle')

  return (
    <section className={`mimi-chat mimi-chat-${variant} w-full max-w-full min-w-0 min-h-0 flex flex-col h-full gap-2 overflow-hidden`} aria-labelledby={`mimi-title-${variant}`}>
      <MimiBackdrop active={current.messages.length > 0} />
      <div className={`mimi-chat-heading ${variant === 'dock' ? 'mimi-chat-heading-dock' : ''}`}>
        <div className="flex min-w-0 items-center gap-2"><MimiAvatar size="xs" state={mimiState} /><h3 id={`mimi-title-${variant}`} className="truncate text-xs font-semibold">{current.title ?? 'Mimi'}</h3></div>
      <details className="mimi-context-chip text-xs" data-testid="mimi-run-context-inspector">
        <summary className="cursor-pointer font-semibold"><span>Ngữ cảnh</span><ChevronDown className="size-3" /></summary><div className="mimi-context-popover">
        <p className="mt-2 text-xs text-muted-foreground">Đây là receipt server của lượt gần nhất, khác với dữ liệu chỉ được mở trong rail. Số upper bound dùng byte UTF-8 làm ước lượng bảo thủ, không phải token do provider báo. Nội dung reasoning ẩn không được hiển thị.</p>
        {latestContext ? (
          <dl className="mt-2 grid gap-2 text-xs sm:grid-cols-2">
            <div><dt>Model / effort yêu cầu</dt><dd>{String((latestContext.payload.route as Record<string, unknown> | undefined)?.requested_model ?? 'Chưa có')} / {String((latestContext.payload.route as Record<string, unknown> | undefined)?.requested_effort ?? 'Chưa có')}</dd></div>
            <div><dt>Input upper bound / context limit / output reserve</dt><dd>{String((latestContext.payload.budget as Record<string, unknown> | undefined)?.serialized_input_upper_bound ?? 'Chưa có')} / {String((latestContext.payload.budget as Record<string, unknown> | undefined)?.context_limit ?? 'Chưa có')} / {String((latestContext.payload.budget as Record<string, unknown> | undefined)?.output_reserve ?? 'Chưa có')}</dd></div>
            <div><dt>Transcript range / checkpoint frontier</dt><dd>{JSON.stringify(latestContext.payload.transcript_range)} / {String(latestContext.payload.checkpoint_frontier ?? 0)}</dd></div>
            <div className="min-w-0"><dt>Manifest hash</dt><dd className="break-all">{String(latestContext.payload.manifest_sha256 ?? 'Chưa có')}</dd></div>
          </dl>
        ) : <p className="mt-2 text-xs">Lượt này chưa có manifest được ghi nhận; không suy ra đã dispatch.</p>}
        {latestCheckpoint ? <p className="mt-2 text-xs">Checkpoint đã activate tới message {String(latestCheckpoint.payload.frontier ?? '?')}, gồm {String(latestCheckpoint.payload.source_count ?? '?')} nguồn. Metadata của receipt; bản tóm tắt hiện hành có thể mở bên dưới.</p> : <p className="mt-2 text-xs">Chưa có checkpoint activate trong các receipt đang hiển thị.</p>}
        <MimiRunObservations observation={latestRun ? current.run_observations?.[latestRun.id] : undefined} calls={(current.provider_calls ?? []).filter((call) => call.run_id === latestRun?.id)} />
        <MimiCheckpointViewer key={current.id} conversationId={current.id} frontier={Number(latestCheckpoint?.payload.frontier ?? 0)} generation={current.generation} />
        <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(latestContext?.payload.sources ?? [], null, 2)}</pre>
      </div></details>
        {latestRun?.state === 'waiting_confirmation' ? <Badge variant="outline">{pendingPreviewExpired ? 'Preview đã hết hạn' : 'Chờ xác nhận'}</Badge> : null}
        {!online ? <Badge variant="destructive">Mất mạng</Badge> : null}
      </div>

      {runtimeActive ? <div className="mimi-progress px-3 py-2 text-accent-foreground" data-testid="mimi-progress" data-phase={streamedText ? 'streaming' : mimiState}><div className="flex items-center justify-between gap-2"><p role="status" className="min-w-0 text-xs"><span className="mimi-thinking-dots" aria-hidden="true"><i /><i /><i /></span>{streamedText ? 'Mimi đang trả lời' : runStage === 'Sẵn sàng' && durableRunActive ? 'Mimi đang làm việc trên server' : runStage} · {elapsedLabel(elapsed)}</p>{cancelRunId ? <Button size="icon" variant="ghost" aria-label="Huỷ run ngay" disabled={cancel.isPending || cancelRequestedRunId === cancelRunId} onClick={() => cancel.mutate(cancelRunId)}><Square className="size-4" /></Button> : null}</div>{cancelRequestedRunId === cancelRunId && cancelRunId ? <p role="status" className="text-xs">Đã gửi yêu cầu hủy; chờ trạng thái server.</p> : null}<details className="text-xs"><summary className="cursor-pointer">Chi tiết tiến trình</summary><p className="mt-2">Đóng chat không dừng run. Hủy gửi lệnh dừng; lời gọi đã dispatch có thể vẫn trả về.</p>{cancelRunId ? pause.data?.run_id === cancelRunId && pause.data.pause_requested ? <p role="status" className="mt-2" data-testid="mimi-pause-acknowledgment">Đã nhận yêu cầu tạm dừng sau bước hiện tại; run chưa dừng.</p> : <Button className="mt-2" size="sm" variant="outline" disabled={pause.isPending || cancel.isPending} onClick={() => pause.mutate(cancelRunId)}>Tạm dừng sau bước này</Button> : null}</details></div> : null}

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

      {latestRun?.error_code === 'mimi_compaction_required_unactivated' ? (
        <div role="alert" className="rounded-lg border border-warn/40 bg-warn-bg p-3 text-sm">
          <p className="font-semibold">Context cần compact nhưng checkpoint chưa được kích hoạt.</p>
          <p className="mt-1 text-xs">Mimi đã dừng trước khi gọi main và không tự gọi helper lại. Mở hội thoại mới để tiếp tục. Nếu helper trước có outcome unknown, mở lượt đó và Reconcile trước khi xử lý tiếp.</p>
        </div>
      ) : null}
      {latestRun?.state === 'halted' && latestRun.error_code?.startsWith('compaction_') ? (
        <div role="alert" className="rounded-lg border border-warn/40 bg-warn-bg p-3 text-sm">
          <p className="font-semibold">Mimi chưa thu gọn được lịch sử nên lượt này đã dừng.</p>
          <p className="mt-1 text-xs">Lịch sử gốc vẫn được giữ nguyên; Mimi không tự gọi helper lại trên cùng context. Bạn có thể mở hội thoại mới. Nếu kết quả provider chưa rõ, cần Reconcile ở lượt bị lỗi.</p>
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

      {latestRun?.error_code === 'provider_result_unavailable_after_reconcile' ? (
        <div role="alert" className="rounded-lg border border-warn/40 bg-warn-bg p-3 text-sm">
          <p className="font-semibold">Provider đã hoàn tất, nhưng Mimi chưa lấy lại được câu trả lời.</p>
          <p className="mt-1 text-xs">Mimi đã xác minh lượt gọi kết thúc; chưa có nội dung hợp lệ để tiếp tục. Hệ thống không tự gửi lại. Nếu bạn gửi yêu cầu mới, đó là một lượt model mới có thể phát sinh chi phí.</p>
        </div>
      ) : null}
      {latestRun?.error_code === 'provider_reconciliation_failed' ? (
        <div role="alert" className="rounded-lg border border-warn/40 bg-warn-bg p-3 text-sm">
          <p className="font-semibold">Provider đã dừng và chưa trả kết quả dùng được.</p>
          <p className="mt-1 text-xs">Mimi không tự gửi lại lượt đã huỷ, bị cắt hoặc thất bại. Bạn có thể điều chỉnh yêu cầu rồi bắt đầu lượt mới.</p>
        </div>
      ) : null}
      {latestRun?.error_code === 'change_set_source_stale' ? (
        <div role="alert" className="rounded-lg border border-warn/40 bg-warn-bg p-3 text-sm" data-testid="mimi-source-stale-notice">
          <p className="font-semibold">Dữ liệu nguồn đã thay đổi; Mimi chưa tạo Task.</p>
          <p className="mt-1 text-xs">Phương án cũ đã bị từ chối. Hãy yêu cầu Mimi đọc nguồn mới và chuẩn bị lại đề xuất trước khi xác nhận.</p>
        </div>
      ) : null}

      {latestRunExceedsContext ? (
        <div role="alert" className="rounded-lg border border-warn/40 bg-warn-bg p-3 text-sm" data-testid="mimi-context-limit-notice">
          <p className="font-semibold">Lượt này chưa vừa giới hạn context đã chọn.</p>
          <p className="mt-1 text-xs">Mimi giữ lịch sử và checkpoint hợp lệ, không tự gửi lại. Bạn có thể tăng giới hạn trong Cấu hình Mimi nếu model hỗ trợ, hoặc mở hội thoại mới. Ngay cả sau thu gọn, policy, tools, ràng buộc và tin nhắn hiện tại vẫn cần đủ chỗ.</p>
        </div>
      ) : null}



      {!online ? (
        <p role="status" className="rounded-lg bg-warn-bg p-3 text-sm text-foreground">
          Bạn đang offline. Draft được giữ trên màn hình và chưa được lưu ở trình duyệt.
        </p>
      ) : null}

      {current.messages.length > 0 ? (
        <div className="flex justify-end">
          <Button size="sm" variant="outline" onClick={() => { followLatest.current = true; transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: 'auto' }) }}>
            Xem lượt mới nhất
          </Button>
        </div>
      ) : null}

      <div ref={transcriptRef} onScroll={(event) => { const el = event.currentTarget; followLatest.current = el.scrollHeight - el.clientHeight - el.scrollTop < 48 }} className={`mimi-transcript flex-1 min-h-0 space-y-4 overflow-y-auto overscroll-contain ${current.messages.length === 0 ? 'mimi-transcript-empty' : ''}`} data-testid="mimi-messages">
        {current.messages.length === 0 ? (
          <div className="mimi-welcome" data-testid="mimi-welcome"><MimiAvatar size="xl" className="mimi-welcome-avatar" /><h2>Chào bạn,<br className="mimi-dock-linebreak" /> vào việc thôi</h2><div className="mimi-welcome-suggestions"><Button type="button" variant="outline" onClick={() => { setDraft('Mimi có thể làm gì?'); messageInputRef.current?.focus() }}><Sparkles className="size-4" />Mimi có thể làm gì?</Button><Button type="button" variant="outline" onClick={() => { setDraft('Tư vấn mình xếp lại lịch'); messageInputRef.current?.focus() }}><CalendarDays className="size-4" />Tư vấn mình xếp lại lịch</Button></div></div>
        ) : current.messages.map((message) => isVerifiedServerNotice(message) ? (
          <MimiSystemNotice key={message.id} message={message} />
        ) : (
          <article
            key={message.id}
            className={message.role === 'user'
              ? 'mimi-message mimi-message-user'
              : 'mimi-message mimi-message-assistant'}
          >
            {message.role === 'assistant' ? <MimiAvatar className="mimi-answer-avatar" /> : null}
            <div className={message.role === 'assistant' ? 'mimi-answer-column min-w-0' : 'min-w-0'}>
              <div className="mimi-message-body">{message.role === 'user' ? <p className="whitespace-pre-wrap break-words text-sm">{message.content}</p> : <MimiMessageText text={message.content} />}
                <time className="mimi-message-time">{new Date(message.created_at).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}</time>
              </div>
              {message.role === 'assistant' ? <div className="mimi-answer-actions" aria-label={`Hành động câu trả lời ${message.sequence}`}>
                <Button type="button" size="icon" variant="ghost" aria-label={`Sao chép câu trả lời ${message.sequence}`} onClick={() => { void navigator.clipboard.writeText(message.content).then(() => toast.success('Đã sao chép', { duration: 2000 })).catch(() => toast.error('Chưa sao chép được', { duration: 2000 })) }}><Copy className="size-4" /></Button>
                <Button type="button" size="icon" variant="ghost" disabled={feedback.isPending} aria-label={`Hữu ích · câu trả lời ${message.sequence}`} onClick={() => openMessageFeedback(message.id, 'positive')}><ThumbsUp className="size-4" /></Button>
                <Button type="button" size="icon" variant="ghost" disabled={feedback.isPending} aria-label={`Chưa tốt · câu trả lời ${message.sequence}`} onClick={() => openMessageFeedback(message.id, 'negative')}><ThumbsDown className="size-4" /></Button>
              </div> : null}
            </div>
          </article>
        ))}
        {streamedText ? (
          <article aria-live="polite" className="mimi-message mimi-message-assistant mimi-streaming"><MimiAvatar className="mimi-answer-avatar" /><div className="mimi-message-body"><MimiMessageText text={streamedText} /></div>
          </article>
        ) : null}
      </div>

      {pendingChangeSet ? (
        <ChangeSetPreview
          changeSet={pendingChangeSet}
          conversationId={current.id}
          pending={decision.isPending || !!decisionIntent}
          error={decision.isError ? errorMessage(decision.error) : null}
          onRevise={() => startPreviewRevision(pendingChangeSet)}
          onDecision={(choice) => confirmDecision(pendingChangeSet, choice)}
        />
      ) : null}

      {decisionIntent || recoveryNotice ? <div className="rounded-lg border bg-warn-bg p-3 text-sm" data-testid="mimi-unknown-recovery"><p role="status">{recoveryNotice ?? 'Lần xác nhận chưa được đối chiếu. Không tự gửi lại.'}</p>{decisionIntent ? <Button className="mt-2" variant="outline" disabled={decision.isPending || recover.isPending} onClick={() => recover.mutate(decisionIntent)}>{recover.isPending ? 'Đang đọc…' : 'Đọc receipt gốc'}</Button> : null}</div> : null}
      {latestReceipt ? <details className="max-h-40 overflow-auto rounded-lg border bg-card p-2 text-xs" data-testid="mimi-receipt"><summary className="cursor-pointer font-semibold">Đã lưu thay đổi · {typeof latestReceipt.result.count === 'number' ? latestReceipt.result.count : 1} Task</summary><div className="mt-2 flex flex-wrap gap-2"><Button variant="outline" onClick={onOpenTasks}>Mở Task</Button>{latestReceipt.result.undo_available === true ? <Button variant="outline" disabled={undo.isPending || runtimeActive || !!pendingChangeSet || !!decisionIntent} onClick={() => undo.mutate(latestReceipt.id)}>Chuẩn bị hoàn tác</Button> : null}</div><p className="mt-2 break-all text-xs">Receipt {latestReceipt.id}</p><p className="text-xs">Hoàn tác tạo preview mới có kiểm tra phiên bản; cần xác nhận riêng.</p>{undo.isError ? <p role="alert" className="text-bad">{errorMessage(undo.error)}</p> : null}</details> : null}

      {feedbackTargets.length ? (
        <Dialog open={feedbackOpen} onOpenChange={setFeedbackOpen}><DialogContent className="max-h-[90dvh] overflow-y-auto" data-testid="mimi-feedback"><DialogHeader><DialogTitle>Góp ý câu trả lời</DialogTitle><DialogDescription>Feedback được gắn với đúng câu trả lời, run, lần gọi hoặc receipt bạn chọn.</DialogDescription></DialogHeader>
          {feedbackMood === 'positive' ? <div className="space-y-3" data-testid="mimi-positive-feedback">
            <ThumbsUp className="mx-auto size-8 text-primary" />
            <p role="status" className="text-center font-semibold">{feedback.isPending ? 'Đang lưu phản hồi tích cực…' : feedbackAcknowledgment?.conversationId === current.id && feedbackAcknowledgment.targetKey === resolvedFeedbackTargetKey && feedbackAcknowledgment.mood === 'positive' ? 'Đã ghi nhận phản hồi tích cực' : 'Chưa xác nhận phản hồi tích cực đã lưu'}</p>
            <p className="rounded-lg bg-muted p-3 text-sm whitespace-pre-wrap break-words">{current.messages.find((message) => message.id === selectedFeedbackTarget?.target_id)?.content.slice(0, 180) ?? selectedFeedbackTarget?.label ?? 'Mục đang chọn'}</p>
            {feedback.isError ? <p role="alert" className="text-sm text-bad">Chưa xác định kết quả lưu. Khi bấm Hữu ích lại sẽ giữ cùng khóa, không tạo bản ghi mới ngầm.</p> : null}
            <p className="text-sm font-semibold">Bạn có thể chia sẻ thêm (không bắt buộc)</p>
            <div className="grid grid-cols-2 gap-2">{['Rõ ràng', 'Đúng ý', 'Hữu ích', 'Nhanh', 'Dễ hiểu', 'Khác'].map((reason) => <Button type="button" key={reason} variant={feedbackReasons.includes(reason) ? 'selected' : 'outline'} size="sm" aria-pressed={feedbackReasons.includes(reason)} onClick={() => toggleFeedbackReason(reason)}>{reason}</Button>)}</div>
            <Textarea aria-label="Ghi chú phản hồi tích cực" value={feedbackDraft} maxLength={500} onChange={(event) => setFeedbackDraft(event.target.value)} placeholder="Muốn ghi chú thêm? (không bắt buộc)" /><p className="text-right text-xs text-muted-foreground">{feedbackDraft.length}/500</p>
            <p role="status" className="text-xs text-muted-foreground">API hiện chưa sửa/bổ sung phản hồi đã lưu. Chi tiết này là bản nháp; chưa gửi và không tự tạo feedback thứ hai.</p>
            <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setFeedbackOpen(false)}>Để sau</Button><Button type="button" disabled>Gửi bổ sung · chưa hỗ trợ</Button></div>
          </div> : <Card className="border-0 shadow-none">
          <CardHeader>
            <CardTitle>Luồng phản hồi chưa tốt</CardTitle>
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
              <p className="rounded-lg bg-muted p-3 text-sm whitespace-pre-wrap break-words" data-testid="mimi-feedback-target-snippet">{current.messages.find((message) => message.id === selectedFeedbackTarget?.target_id)?.content.slice(0, 180) ?? selectedFeedbackTarget?.label ?? 'Chọn mục cần góp ý'}</p>
              <fieldset className="space-y-2"><legend className="text-sm font-semibold">Vấn đề gặp phải</legend><div className="grid grid-cols-2 gap-2">{['Thiếu chính xác', 'Thiếu ngữ cảnh', 'Khó hiểu', 'Chưa làm đúng yêu cầu', 'Khác'].map((reason) => <Button type="button" key={reason} variant={feedbackReasons.includes(reason) ? 'selected' : 'outline'} size="sm" aria-pressed={feedbackReasons.includes(reason)} onClick={() => toggleFeedbackReason(reason)}>{reason}</Button>)}</div></fieldset>
              <div className="space-y-1.5">
                <label htmlFor="mimi-feedback" className="text-sm font-semibold">Điều gì cần sửa hoặc làm rõ?</label>
                <Textarea
                  id="mimi-feedback"
                  required
                  value={feedbackDraft}
                  maxLength={500}
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
                <p id="mimi-feedback-help" className="flex justify-between text-xs text-muted-foreground"><span>Nội dung được mã hoá khi lưu.</span><span>{feedbackDraft.length}/500</span></p>
              </div>
              <div className="space-y-1.5">
                <label htmlFor="mimi-feedback-expected" className="text-sm font-semibold">Kết quả bạn mong đợi (không bắt buộc)</label>
                <Textarea
                  id="mimi-feedback-expected"
                  value={feedbackExpected}
                  maxLength={500}
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
              <p className="text-right text-xs text-muted-foreground">{feedbackExpected.length}/500</p>
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
          </Card>}
          <MimiFeedbackEvidence conversation={current} target={selectedFeedbackTarget} />
        </DialogContent></Dialog>
      ) : null}

      <form onSubmit={submitMessage} className="mimi-composer shrink-0">
        {revisionTarget && !activeRevision ? (
          <div role="alert" className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-bad-bg p-3 text-sm text-bad">
            <p>Phương án đã đổi hoặc không còn chờ xác nhận. Tin nhắn chưa được gửi; hủy chế độ sửa hoặc chọn phương án đang chờ.</p>
            <Button type="button" size="lg" variant="outline" onClick={() => setRevisionTarget(null)}>Hủy sửa</Button>
          </div>
        ) : null}
        {activeRevision ? (
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-accent p-3 text-sm" role="status" data-testid="mimi-revision-target">
            <p>Đang sửa đúng phương án “{pendingChangeSet ? mimiChangeTitle(pendingChangeSet) : ''}”. Hãy mô tả nội dung cần thay đổi.</p>
            <Button type="button" size="lg" variant="outline" onClick={() => setRevisionTarget(null)}>Hủy sửa</Button>
          </div>
        ) : null}
        <div className="mimi-composer-surface relative flex flex-col rounded-2xl border border-input focus-within:ring-2 focus-within:ring-ring p-2">
      <MimiConfiguration conversationId={current.id} capabilities={capabilities.data} runtimeActive={runtimeActive} open={settingsOpen} onOpenChange={onSettingsOpenChange} onOpenHub={onOpenConfiguration} />
          <Textarea
            rows={1}
            id="mimi-message"
            ref={messageInputRef}
            data-testid="mimi-input"
            aria-label="Nhắn Mimi"
            value={draft}
            maxLength={12_000}
            placeholder={activeRevision
              ? 'Mô tả cách bạn muốn sửa phương án…'
              : 'Nhắn Mimi…'}
            disabled={runtimeActive || !!current.archived_at || !!decisionIntent}
            className="mimi-composer-input w-full resize-none border-none bg-transparent p-1 text-base md:text-sm shadow-none focus-visible:ring-0 focus-visible:outline-none"
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
          <div className="mimi-composer-footer mt-1 flex items-center justify-between pt-1 text-xs text-muted-foreground">
            {current.archived_at ? <span className="text-xs text-muted-foreground">Hội thoại đã lưu · chỉ xem lại.</span> : null}
            <Button
              type="submit"
              size="sm"
              className="mimi-send min-h-11 min-w-11 rounded-full shrink-0"
              disabled={!!decisionIntent || !!current.archived_at || !draft.trim() || runtimeActive || !online || (revisionTarget !== null && !activeRevision)}
            >
              {runtimeActive ? <LoaderCircle className="size-3.5 animate-spin motion-reduce:animate-none" /> : <Send className="size-3.5" />}
              <span className="sr-only">Gửi</span>
            </Button>
          </div>
        </div>
        {send.isError ? <p role="alert" className="mt-1 text-xs text-bad">{errorMessage(send.error)}</p> : null}
      </form>

      <Dialog open={technicalOpen ?? false} onOpenChange={onTechnicalOpenChange}>
        <DialogContent className="max-h-[85dvh] overflow-y-auto" data-testid="mimi-technical-dialog" onCloseAutoFocus={(event) => { if (onTechnicalCloseFocus) { event.preventDefault(); onTechnicalCloseFocus() } }}>
          <DialogHeader><DialogTitle>Chi tiết kỹ thuật</DialogTitle><DialogDescription>Receipt đã được server cho phép đọc của hội thoại đang chọn. Không hiển thị reasoning ẩn.</DialogDescription></DialogHeader>
          <MimiRunObservations observation={latestRun ? current.run_observations?.[latestRun.id] : undefined} calls={(current.provider_calls ?? []).filter((call) => call.run_id === latestRun?.id)} />
          <MimiCheckpointViewer key={current.id} conversationId={current.id} frontier={Number(latestCheckpoint?.payload.frontier ?? 0)} generation={current.generation} />
          <p className="text-xs font-semibold">Event đang hiển thị ({current.events.length}) · 30 event cuối trong view</p>
          <ol className="space-y-1 text-xs text-muted-foreground">{current.events.slice(-30).map((event) => <li key={event.id}>{event.kind}</li>)}</ol>
        </DialogContent>
      </Dialog>
    </section>
  )
}
