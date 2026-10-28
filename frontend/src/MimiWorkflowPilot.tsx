import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { ApiError, TimeoutError } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  advanceWorkflowPilotRun,
  createWorkflowPilotRun,
  getWorkflowPilotRun,
  listWorkflowPilotRuns,
  listWorkflowPilotTasks,
  type WorkflowPilotStatus,
} from '@/workflow-pilot-api'

const labels: Record<string, string> = {
  query: 'Đang đọc Task', group: 'Đang nhóm Task', draft: 'Đang tạo bản nháp',
  direction: 'Chờ chọn hướng', materialize: 'Đang tạo preview', confirmation: 'Chờ xác nhận chính xác',
  execute: 'Đang ghi Task', succeeded: 'Đã hoàn tất', expired: 'Preview đã hết hạn',
  cancelled: 'Đã huỷ', reconcile: 'Cần đối soát', repreview: 'Cần tạo preview mới',
}
const terminal = new Set(['succeeded', 'expired', 'cancelled', 'repreview'])
const pendingStorageKey = 'mimi-workflow-pilot-pending-run'
type PendingRequest = { runId: string; taskIds: string[]; engine: 'graph' | 'control' }

function readPendingRequest(): PendingRequest | null {
  try {
    const value = window.sessionStorage.getItem(pendingStorageKey)
    if (!value) return null
    const parsed: unknown = JSON.parse(value)
    if (typeof parsed !== 'object' || parsed === null) return null
    const request = parsed as Partial<PendingRequest>
    if (typeof request.runId !== 'string' || !Array.isArray(request.taskIds)
      || !request.taskIds.every((id) => typeof id === 'string')
      || (request.engine !== 'graph' && request.engine !== 'control')) return null
    return request as PendingRequest
  } catch { return null }
}

function explain(error: unknown) {
  if (error instanceof TimeoutError) return 'Hết thời gian chờ. Run có thể đã được nhận; dùng Tải lại trạng thái để kiểm tra, không gửi lại.'
  if (error instanceof ApiError && error.status === 409) return `Máy chủ dừng thao tác (${error.message}). Tải lại trạng thái để xem hướng xử lý.`
  if (error instanceof ApiError) return `Không thực hiện được (${error.message}). Tải lại trạng thái trước khi quyết định bước tiếp.`
  return 'Không kết nối được. Tải lại trạng thái để kiểm tra; ứng dụng không tự gửi lại thao tác.'
}

export function MimiWorkflowPilot() {
  const client = useQueryClient()
  const [selected, setSelected] = useState<string[]>([])
  const [engine, setEngine] = useState<'graph' | 'control'>('graph')
  const [run, setRun] = useState<WorkflowPilotStatus | null>(null)
  const [pendingRequest, setPendingRequest] = useState<PendingRequest | null>(readPendingRequest)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [definitiveRejection, setDefinitiveRejection] = useState(false)
  const pendingRunId = pendingRequest?.runId ?? null
  const visibleSelection = pendingRequest?.taskIds ?? selected
  const visibleEngine = pendingRequest?.engine ?? engine
  const tasks = useQuery({ queryKey: ['mimi', 'workflow-pilot', 'tasks'], queryFn: listWorkflowPilotTasks, retry: false })
  const runs = useQuery({ queryKey: ['mimi', 'workflow-pilot', 'runs'], queryFn: listWorkflowPilotRuns, retry: false })

  const refresh = async () => {
    setError(null)
    setBusy(true)
    try {
      const id = pendingRunId ?? run?.run_id
      if (id) {
        setRun(await getWorkflowPilotRun(id))
        if (id === pendingRunId) {
          setPendingRequest(null)
          window.sessionStorage.removeItem(pendingStorageKey)
        }
      }
      await client.invalidateQueries({ queryKey: ['mimi', 'workflow-pilot', 'runs'] })
    } catch (cause) { setError(explain(cause)) }
    finally { setBusy(false) }
  }
  const start = async () => {
    const request = pendingRequest ?? { runId: crypto.randomUUID(), taskIds: selected, engine }
    setPendingRequest(request)
    window.sessionStorage.setItem(pendingStorageKey, JSON.stringify(request))
    setError(null)
    setDefinitiveRejection(false)
    setBusy(true)
    try {
      setRun(await createWorkflowPilotRun(request.runId, request.taskIds, request.engine))
      setPendingRequest(null)
      window.sessionStorage.removeItem(pendingStorageKey)
      await client.invalidateQueries({ queryKey: ['mimi', 'workflow-pilot', 'runs'] })
    } catch (cause) {
      setError(explain(cause))
      setDefinitiveRejection(cause instanceof ApiError && cause.status === 409 && [
        'public_source_required', 'source_requires_repreview', 'active_quota_exceeded',
        'pilot_identity_quota_exceeded',
      ].includes(cause.message))
    }
    finally { setBusy(false) }
  }
  const advance = async (action: Parameters<typeof advanceWorkflowPilotRun>[1]) => {
    if (!run) return
    setError(null)
    setBusy(true)
    try {
      setRun(await advanceWorkflowPilotRun(run, action))
      await client.invalidateQueries({ queryKey: ['mimi', 'workflow-pilot', 'runs'] })
    } catch (cause) { setError(explain(cause)) }
    finally { setBusy(false) }
  }
  const resume = async (id: string) => {
    setError(null)
    setBusy(true)
    try {
      setRun(await getWorkflowPilotRun(id))
      if (id === pendingRunId) {
        setPendingRequest(null)
        window.sessionStorage.removeItem(pendingStorageKey)
      }
    } catch (cause) { setError(explain(cause)) }
    finally { setBusy(false) }
  }

  const phase = run?.phase ?? ''
  const preview = run?.preview
  const previewComplete = Boolean(preview
    && preview.sources.length > 0
    && preview.sources.length === preview.operations.length
    && new Set(preview.sources.map((source) => source.id)).size === preview.sources.length
    && preview.sources.every((source) => preview.operations.some((operation) => operation.id === source.id))
    && new Set(preview.operations.map((operation) => operation.id)).size === preview.operations.length)
  return <Card data-testid="mimi-workflow-pilot" className="mt-4 min-w-0">
    <CardHeader>
      <div className="flex flex-wrap items-center gap-2"><Badge variant="outline">Thử nghiệm cục bộ</Badge><Badge variant="secondary">{run?.provider_mode === 'live' ? 'Provider thật · bản nháp chỉ để tham khảo' : 'Provider tổng hợp xác định'}</Badge></div>
      <CardTitle>Quy trình Task Mimi</CardTitle>
      <CardDescription>Chọn tối đa 16 Task công khai. Mỗi bước ghi dữ liệu đều cần bạn xác nhận.</CardDescription>
    </CardHeader>
    <CardContent className="space-y-4 text-sm">
      {busy ? <p role="status" aria-live="polite">Đang chờ máy chủ xử lý… Ứng dụng không tự gửi lại thao tác.</p> : null}
      {tasks.isPending ? <p role="status">Đang tải Task…</p> : null}
      {tasks.isError ? <div role="alert" className="space-y-2 text-bad"><p>Không tải được Task.</p><Button type="button" variant="outline" className="min-h-11" onClick={() => void tasks.refetch()}>Tải lại Task</Button></div> : null}
      {tasks.data ? <>
        <p aria-live="polite">Đã chọn {visibleSelection.length} / 16 Task</p>
        <div className="max-h-64 space-y-2 overflow-y-auto">
          {tasks.data.items.map((task) => {
            const active = visibleSelection.includes(task.id)
            return <Button key={task.id} type="button" variant={active ? 'selected' : 'outline'} aria-pressed={active}
              disabled={Boolean(pendingRequest) || (!active && visibleSelection.length >= 16)} className="h-auto min-h-11 w-full justify-start whitespace-normal text-left"
              onClick={() => setSelected((ids) => active ? ids.filter((id) => id !== task.id) : [...ids, task.id])}>
              {task.title}
            </Button>
          })}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={visibleEngine} disabled={Boolean(pendingRequest)} onValueChange={(value) => setEngine(value as 'graph' | 'control')}>
            <SelectTrigger aria-label="Chọn engine" className="min-h-11 w-full sm:w-52"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem className="min-h-11" value="graph">LangGraph</SelectItem><SelectItem className="min-h-11" value="control">Control</SelectItem></SelectContent>
          </Select>
          <Button type="button" className="min-h-11" disabled={busy || (!pendingRunId && selected.length < 1) || Boolean(run && !terminal.has(run.phase))} onClick={() => void start()}>
            {pendingRunId ? 'Gửi lại cùng run ID' : 'Bắt đầu quy trình'}
          </Button>
          <Button type="button" variant="outline" className="min-h-11" disabled={busy} onClick={() => void refresh()}>Tải lại trạng thái</Button>
          {pendingRequest && definitiveRejection ? <Button type="button" variant="outline" className="min-h-11" disabled={busy} onClick={() => {
            setPendingRequest(null)
            window.sessionStorage.removeItem(pendingStorageKey)
            setSelected([])
            setDefinitiveRejection(false)
            setError(null)
            void tasks.refetch()
          }}>Bỏ lựa chọn đã bị từ chối và tải lại Task</Button> : null}
        </div>
      </> : null}

      {runs.isPending ? <p role="status">Đang tải run gần đây…</p> : null}
      {runs.data?.items.length ? <section aria-label="Run gần đây" className="space-y-2">
        <h3 className="font-semibold">Run gần đây</h3>
        {runs.data.items.map((item) => <Button key={item.run_id} type="button" variant="outline" disabled={busy} className="min-h-11 w-full justify-between gap-2 whitespace-normal"
          onClick={() => void resume(item.run_id)}><span className="break-all">Mở {item.run_id}</span><span>{labels[item.phase] ?? item.phase}</span></Button>)}
      </section> : null}
      {runs.isError ? <p role="alert" className="text-bad">Không tải được danh sách run. Có thể tải lại trạng thái.</p> : null}
      {error ? <p role="alert" className="break-words text-bad">{error}</p> : null}
      {run ? <section className="space-y-3 rounded-xl border p-3" data-testid="workflow-pilot-run">
        <div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">Trạng thái quy trình</h3><Badge>{labels[phase] ?? phase}</Badge><Badge variant="outline">{run.engine === 'graph' ? 'LangGraph' : 'Control'}</Badge><span className="break-all text-xs">{run.run_id}</span></div>
        <p>Chế độ provider: {run.provider_mode === 'deterministic' ? 'Tổng hợp xác định' : run.provider_mode}</p>
        <p>Số lần gọi provider: {run.provider_calls}</p>
        {run.stop_reason ? <p role="status">{run.stop_reason}</p> : null}
        {run.source_visibility_reason ? <p role="status">Nguồn Task đã thay đổi hoặc bị ẩn; nội dung nguồn không được hiển thị.{['provider_outcome_unknown', 'owner_cancelled_provider_unknown'].includes(run.stop_reason ?? '') ? ' Kết quả lần gọi provider trước vẫn chưa rõ và cần đối soát.' : ''}</p> : null}
        {run.preview?.groups.length ? <div><h4 className="font-semibold">Nhóm Task</h4>{run.preview.groups.map((group, index) => <p key={index}>Nhóm {index + 1}: {group.map((id) => tasks.data?.items.find((task) => task.id === id)?.title ?? id).join(', ')}</p>)}</div> : null}
        {run.draft ? <div><h4 className="font-semibold">Bản nháp</h4><p className="whitespace-pre-wrap break-words">{run.draft}</p></div> : null}
        {phase === 'direction' ? <div className="space-y-2"><p>Thao tác máy chủ hỗ trợ: thêm <strong>[planned] </strong> trước mỗi title đang chọn, giữ nguyên nội dung còn lại. Bản nháp không thể đổi thao tác này.</p><Button type="button" className="min-h-11" disabled={busy} onClick={() => void advance({ direction: 'apply_prefix' })}>Duyệt hướng thêm [planned]</Button></div> : null}
        {run.preview ? <div className="space-y-2">
          <h4 className="font-semibold">Đối chiếu trước và sau</h4>
          {run.preview.operations.map((operation) => {
            const source = run.preview?.sources.find((item) => item.id === operation.id)
            return <div key={operation.id} className="rounded-lg border p-3"><p className="break-words"><strong>Trước:</strong> {source?.title ?? 'Không có dữ liệu nguồn'}</p><p className="break-words"><strong>Sau:</strong> {operation.title}</p></div>
          })}
          {!previewComplete ? <p role="alert" className="text-bad">Preview chưa có đủ cặp trước và sau; chưa thể xác nhận.</p> : null}
        </div> : null}
        {phase === 'confirmation' && run.preview_digest && previewComplete
          ? <Button type="button" className="min-h-11" disabled={busy} onClick={() => void advance({ preview_digest: run.preview_digest! })}>Xác nhận đúng preview này</Button> : null}
        {run.receipt ? <div role="status" className="rounded-lg bg-muted p-3"><h4 className="font-semibold">Biên nhận hoàn tất</h4><p>Đã đổi {run.receipt.changed} Task</p><p className="break-all text-xs">Digest: {run.receipt.digest}</p></div> : null}
        {['query', 'group', 'draft', 'materialize', 'execute'].includes(phase) ? <div className="space-y-2"><p role="status">Run đang ở bước xử lý. Tải lại trạng thái để xem tiến độ; chỉ tiếp tục khi máy chủ cho phép resume.</p>{run.can_resume ? <Button type="button" className="min-h-11" disabled={busy} onClick={() => void advance({ resume: true })}>Tiếp tục run</Button> : null}</div> : null}
        {['reconcile', 'repreview', 'expired'].includes(phase) ? <p role="status">Chưa gửi thêm thao tác. Đọc lý do từ máy chủ và chỉ tiếp tục sau khi trạng thái đã rõ.</p> : null}
        {run.can_cancel ? <Button type="button" variant="outline" className="min-h-11" disabled={busy} onClick={() => void advance({ cancel: true })}>Huỷ quy trình</Button> : null}
      </section> : null}
    </CardContent>
  </Card>
}
