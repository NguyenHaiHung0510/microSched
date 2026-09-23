import { useQuery } from '@tanstack/react-query'
import { Activity, CalendarDays, CheckCircle2, CircleDot, FileText, ListTodo, MessageSquareText, PanelRight, ReceiptText } from 'lucide-react'
import { useState } from 'react'

import { apiRequest } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { MimiConversation } from '@/mimi-api'
import { mimiRunLabel, mimiTaskScheduleLabel } from '@/mimi-presentation'
import { NO_POLLING_QUERY_OPTIONS } from '@/query-polling'

type Domain = 'tasks' | 'notes' | 'calendar' | 'tracker'
type RailTab = 'context' | 'preview' | 'run'
type Item = Record<string, unknown>

type ContextBundle = {
  tasks: Item[]
  notes: Item[]
  events: Item[]
  trackers: Item[]
}

function futureWindow() {
  const from = new Date()
  from.setHours(0, 0, 0, 0)
  const to = new Date(from)
  to.setDate(to.getDate() + 31)
  return { from: from.toISOString(), to: to.toISOString() }
}

async function fetchWorkspaceContext(): Promise<ContextBundle> {
  const window = futureWindow()
  const [taskPage, notes, events, trackers] = await Promise.all([
    apiRequest<{ items: Item[] }>('/api/tasks/timeline?status=open&limit=20'),
    apiRequest<{ items: Item[] }>('/api/notes?limit=8&offset=0'),
    apiRequest<{ items: Item[] }>(`/api/calendar/events?from=${encodeURIComponent(window.from)}&to=${encodeURIComponent(window.to)}`),
    apiRequest<{ items: Item[] }>('/api/tracker/trackers'),
  ])
  return { tasks: taskPage.items, notes: notes.items, events: events.items, trackers: trackers.items }
}

function text(value: unknown, fallback = 'Không có tiêu đề') {
  return typeof value === 'string' && value.trim() ? value : fallback
}

function ContextPanel({ onOpenDomain }: { onOpenDomain: (domain: Domain) => void }) {
  const context = useQuery({ queryKey: ['mimi', 'workspace-context'], queryFn: fetchWorkspaceContext, ...NO_POLLING_QUERY_OPTIONS })
  const groups: Array<{ domain: Domain; label: string; icon: typeof ListTodo; items: Item[]; title: (item: Item) => string }> = [
    { domain: 'tasks', label: 'Task', icon: ListTodo, items: context.data?.tasks ?? [], title: (item) => text(item.title) },
    { domain: 'calendar', label: 'Lịch 30 ngày tới', icon: CalendarDays, items: context.data?.events ?? [], title: (item) => text(item.title ?? item.summary, 'Sự kiện') },
    { domain: 'notes', label: 'Ghi chú gần đây', icon: FileText, items: context.data?.notes ?? [], title: (item) => text(item.title ?? item.body_md, 'Ghi chú không tiêu đề') },
    { domain: 'tracker', label: 'Tracker', icon: Activity, items: context.data?.trackers ?? [], title: (item) => text(item.name) },
  ]
  if (context.isPending) return <p role="status" className="py-8 text-center text-sm text-muted-foreground">Đang mở dữ liệu microSched…</p>
  if (context.isError) return <div className="space-y-3"><p role="alert" className="text-sm text-bad">Không tải được context rail.</p><Button variant="outline" onClick={() => void context.refetch()}>Thử lại</Button></div>
  return <div className="space-y-4">{groups.map(({ domain, label, icon: Icon, items, title }) => <section key={domain} aria-labelledby={`mimi-context-${domain}`} className="space-y-2"><div className="flex items-center justify-between gap-2"><h4 id={`mimi-context-${domain}`} className="flex items-center gap-2 text-sm font-extrabold"><Icon className="size-4 text-primary" aria-hidden="true" />{label}</h4><Button size="sm" variant="ghost" onClick={() => onOpenDomain(domain)}>Mở đầy đủ</Button></div>{items.length ? <ul className="space-y-1.5">{items.slice(0, 4).map((item, index) => <li key={text(item.id, `${domain}-${index}`)} className="rounded-lg bg-muted/60 p-2.5 text-sm"><p className="line-clamp-2 font-semibold">{title(item)}</p>{domain === 'calendar' && item.starts_at ? <p className="mt-1 text-xs text-muted-foreground">{new Date(String(item.starts_at)).toLocaleString('vi-VN')}</p> : null}</li>)}</ul> : <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">Chưa có dữ liệu trong phạm vi này.</p>}</section>)}</div>
}

function PreviewPanel({ conversation }: { conversation: MimiConversation | null | undefined }) {
  const pending = [...(conversation?.change_sets ?? [])].reverse().find((item) => item.state === 'pending')
  if (!pending) return <div className="py-8 text-center"><ReceiptText className="mx-auto mb-2 size-7 text-muted-foreground" /><p className="font-semibold">Không có preview chờ duyệt</p><p className="mt-1 text-xs text-muted-foreground">Preview mới sẽ mở ở đây mà không che transcript.</p></div>
  return <div className="space-y-3"><div className="flex flex-wrap gap-2"><Badge>Chờ xác nhận</Badge><Badge variant="outline">{pending.operation.tool}</Badge></div><div className="rounded-lg bg-primary/5 p-3"><p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Thay đổi đề xuất</p><p className="mt-1 font-bold">{pending.operation.args.title}</p></div><dl className="space-y-2 text-xs"><div><dt className="font-semibold">Lịch Task</dt><dd>{mimiTaskScheduleLabel(pending.operation.args)}</dd></div><div><dt className="font-semibold">Preview hết hạn</dt><dd>{new Date(pending.expires_at).toLocaleString('vi-VN')}</dd></div><div><dt className="font-semibold">Digest</dt><dd className="break-all font-mono">{pending.digest}</dd></div><div><dt className="font-semibold">Quyền ghi</dt><dd>Chưa ghi gì khi bạn chưa xác nhận.</dd></div></dl></div>
}

function RunPanel({ conversation }: { conversation: MimiConversation | null | undefined }) {
  const run = conversation?.runs.at(-1)
  const events = run ? conversation?.events.filter((item) => item.run_id === run.id) ?? [] : []
  if (!run) return <div className="py-8 text-center"><CircleDot className="mx-auto mb-2 size-7 text-muted-foreground" /><p className="font-semibold">Chưa có run</p></div>
  const manifest = [...events].reverse().find((event) => event.kind === 'context.manifest')?.payload
  const sources = Array.isArray(manifest?.sources) ? manifest.sources as Array<Record<string, unknown>> : []
  const providerCall = conversation?.provider_calls?.filter((call) => call.run_id === run.id).at(-1)
  const reported = providerCall?.usage ?? {}
  return <div className="space-y-3">
    <div className="flex items-center justify-between gap-2"><Badge variant="outline">{mimiRunLabel(run.state)}</Badge><span className="text-xs text-muted-foreground">Run {run.generation}</span></div>
    <dl className="grid gap-2 text-xs">
      <div className="rounded-lg bg-muted/60 p-3"><dt className="font-semibold">Bắt đầu</dt><dd>{new Date(run.created_at).toLocaleString('vi-VN')}</dd></div>
      <div className="rounded-lg bg-muted/60 p-3"><dt className="font-semibold">Deadline</dt><dd>{new Date(run.deadline).toLocaleString('vi-VN')}</dd></div>
    </dl>
    <details className="rounded-lg border p-3 text-xs" data-testid="mimi-context-inspector">
      <summary className="cursor-pointer font-semibold">Route, nguồn context và mức dùng</summary>
      <dl className="mt-3 space-y-2">
        <div><dt className="font-semibold">Model / effort yêu cầu</dt><dd>{providerCall?.requested_model ?? String(manifest?.requested_model ?? 'Chưa có')} · {providerCall?.requested_effort ?? String(manifest?.requested_effort ?? 'chưa rõ')}</dd></div>
        <div><dt className="font-semibold">Route thực tế</dt><dd>{providerCall?.actual_model ?? 'Chưa có receipt'} · {providerCall?.actual_provider ?? 'Chưa rõ provider'}</dd></div>
        <div><dt className="font-semibold">Context đã gửi / giới hạn</dt><dd>{typeof manifest?.input_upper_bound === 'number' ? `${manifest.input_upper_bound.toLocaleString('vi-VN')} byte (giới hạn trên)` : 'Chưa có'} / {typeof manifest?.context_limit === 'number' ? `${manifest.context_limit.toLocaleString('vi-VN')} token` : 'chưa rõ'}</dd></div>
        <div><dt className="font-semibold">Checkpoint</dt><dd>{typeof manifest?.checkpoint_frontier === 'number' && manifest.checkpoint_frontier > 0 ? `Đến message ${manifest.checkpoint_frontier}` : 'Chưa compact'}</dd></div>
        <div><dt className="font-semibold">Token / cache / chi phí do nguồn báo</dt><dd>{typeof reported.total_tokens === 'number' ? `${reported.total_tokens.toLocaleString('vi-VN')} token` : 'Chưa có token'} · {typeof reported.cache_read_tokens === 'number' ? `${reported.cache_read_tokens.toLocaleString('vi-VN')} cache read` : 'cache chưa báo'} · {typeof reported.cost === 'number' ? `$${reported.cost.toFixed(5)}` : 'chi phí chưa báo'}</dd></div>
      </dl>
      <div className="mt-3 space-y-2">
        <p className="font-semibold">Nguồn được đưa vào model</p>
        {sources.length ? <ul className="space-y-1">{sources.map((source, index) => <li key={`${String(source.source_id)}-${index}`} className="rounded-lg bg-muted/60 p-2"><p className="font-medium break-all">{String(source.source_id)}</p><p>{String(source.coverage)} · {String(source.count)} mục · {source.data_as_of ? new Date(String(source.data_as_of)).toLocaleString('vi-VN') : 'không có mốc nguồn'}</p>{Array.isArray(source.omitted_fields) && source.omitted_fields.length ? <p className="text-muted-foreground">Không gửi: {source.omitted_fields.join(', ')}</p> : null}</li>)}</ul> : <p className="text-muted-foreground">Chưa có manifest nguồn.</p>}
      </div>
    </details>
    <ol className="space-y-2">{events.slice(-8).map((event) => <li key={event.id} className="flex items-center gap-2 text-xs"><CheckCircle2 className="size-3.5 text-primary" /><span>{event.kind}</span></li>)}</ol>
  </div>
}

export function MimiContextRail({ conversation, onOpenDomain }: { conversation: MimiConversation | null | undefined; onOpenDomain: (domain: Domain) => void }) {
  const [tab, setTab] = useState<RailTab>('context')
  return <Card className="min-w-0 content-start" data-testid="mimi-context-rail"><CardHeader><div className="flex items-center gap-2"><PanelRight className="size-5 text-primary" aria-hidden="true" /><CardTitle>Workspace</CardTitle></div><CardDescription>Xem microSched và trạng thái Mimi cạnh conversation.</CardDescription></CardHeader><CardContent className="space-y-4"><div className="grid grid-cols-3 gap-1" role="tablist" aria-label="Nội dung workspace"><Button size="sm" role="tab" aria-selected={tab === 'context'} variant={tab === 'context' ? 'selected' : 'ghost'} onClick={() => setTab('context')}>Context</Button><Button size="sm" role="tab" aria-selected={tab === 'preview'} variant={tab === 'preview' ? 'selected' : 'ghost'} onClick={() => setTab('preview')}>Preview</Button><Button size="sm" role="tab" aria-selected={tab === 'run'} variant={tab === 'run' ? 'selected' : 'ghost'} onClick={() => setTab('run')}>Run</Button></div><div role="tabpanel">{tab === 'context' ? <ContextPanel onOpenDomain={onOpenDomain} /> : null}{tab === 'preview' ? <PreviewPanel conversation={conversation} /> : null}{tab === 'run' ? <RunPanel conversation={conversation} /> : null}</div><p className="border-t pt-3 text-xs text-muted-foreground"><MessageSquareText className="mr-1 inline size-3.5" />Bạn nhìn thấy ở rail không đồng nghĩa nội dung tự động được gửi cho model.</p></CardContent></Card>
}
