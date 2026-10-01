import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, ChevronLeft, ChevronRight, Edit3, Plus, Trash2 } from 'lucide-react'

import { apiRequest } from '@/api'
import { queuedRequest } from '@/lib/queued-mutation'
import type { Json, OutboxRow } from '@/lib/outbox-db'
import { uuidv7 } from '@/lib/uuidv7'
import { useDomainReadControl } from '@/lib/use-domain-outbox'
import { EventForm } from '@/EventForm'
import {
  addVietnamDays,
  eventDialogErrorMessage,
  formatVietnamDate,
  formatVietnamTime,
  groupEvents,
  importConflict,
  importErrorMessage,
  rangeQuery,
  sourceColorToken,
  todayInVietnam,
  type CalendarEvent,
  type CalendarSource,
  type ImportReport,
} from '@/calendar-ui'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { FilePicker } from '@/components/ui/file-picker'
import { CalendarScrollView } from '@/CalendarScrollView'
import { CALENDAR_QUERY_OPTIONS } from '@/calendar-queries'
import { SourceForm } from '@/SourceForm'

type SourceEnvelope = { items: CalendarSource[] }
type EventEnvelope = { items: CalendarEvent[] }
type ImportRequestReceipt = {
  sourceId: string
  startedAt: number
  acknowledged: boolean
  acknowledgedResponse?: unknown
}
type ConfirmState =
  | { kind: 'source'; source: CalendarSource }
  | { kind: 'event'; event: CalendarEvent }
  | null

// eslint-disable-next-line react-refresh/only-export-components -- pure report validator is unit-tested separately.
export function validateImportReport(value: unknown): ImportReport | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return null
  const report = value as Record<string, unknown>
  const counters = [report.parsed, report.inserted, report.removed, report.duplicates]
  if (!counters.every((count) => Number.isSafeInteger(count) && (count as number) >= 0)) return null
  if (!Array.isArray(report.skipped) || !report.skipped.every((reason) => typeof reason === 'string')) return null
  const parsed = report.parsed as number
  const inserted = report.inserted as number
  const duplicates = report.duplicates as number
  const removed = report.removed as number
  if (parsed !== inserted + duplicates + report.skipped.length) return null
  return {
    parsed,
    inserted,
    removed,
    duplicates,
    skipped: report.skipped as string[],
  }
}

// eslint-disable-next-line react-refresh/only-export-components -- pure correlation predicate is unit-tested separately.
export function matchesImportAcknowledgement(
  request: Pick<ImportRequestReceipt, 'sourceId' | 'startedAt'>,
  row: Pick<OutboxRow, 'operation_kind' | 'entity_id' | 'created_at'>,
): boolean {
  return row.operation_kind === 'calendar.import' && row.entity_id === request.sourceId &&
    row.created_at >= request.startedAt
}

const VIEW_KEY = 'microsched:calendar-view'

async function getSources(signal?: AbortSignal): Promise<SourceEnvelope> {
  return apiRequest<SourceEnvelope>('/api/calendar/sources', { signal })
}

async function getEvents(startDay: string, signal?: AbortSignal): Promise<EventEnvelope> {
  const query = rangeQuery(startDay)
  return apiRequest<EventEnvelope>(
    `/api/calendar/events?from=${encodeURIComponent(query.from)}&to=${encodeURIComponent(query.to)}`,
    { signal },
  )
}

function fileBaseName(file: File): string {
  return file.name.replace(/\.ics$/i, '')
}

function validateFile(file: File): string | null {
  if (!/\.ics$/i.test(file.name)) return 'Chỉ nhận file .ics. Chọn lại file lịch.'
  if (file.size > 1_048_576) return 'File vượt quá 1 MB. Chọn file nhỏ hơn rồi thử lại.'
  return null
}


// ⚡ Bolt: Wrapped EventCard in React.memo to prevent unnecessary re-renders.
// EventCard components are rendered in lists within CalendarScreen.
// When parent state changes (like opening a dialog), we want to avoid re-rendering
// all event cards. By extracting this component and memoizing the props (using useCallback
// for functions passed as props), we ensure that unchanged event cards do not re-render.
// Impact: Reduces re-renders significantly during parent state changes.
const EventCard = memo(function EventCard({
  event,
  source,
  openEditEvent,
  setConfirm,
}: {
  event: CalendarEvent
  source: CalendarSource | undefined
  openEditEvent: (event: CalendarEvent) => void
  setConfirm: (state: ConfirmState) => void
}) {
  return (
    <Card
      data-testid="calendar-event-card"
      data-event-id={event.id}
      className="gap-3 p-4 shadow-1 ring-0"
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="mt-1 size-3 shrink-0 rounded-full"
          style={{ backgroundColor: sourceColorToken(source?.color ?? null) }}
        />
        <div className="min-w-0 flex-1 space-y-1">
          <p className="break-words text-base font-bold">{event.title}</p>
          <p className="text-sm text-muted-foreground">
            {formatVietnamTime(event)} · {source?.name ?? 'Nguồn không còn'}
          </p>
          {event.location ? <p className="break-words text-sm">{event.location}</p> : null}
          {event.description_md ? (
            <p className="whitespace-pre-wrap break-words text-sm text-muted-foreground">
              {event.description_md}
            </p>
          ) : null}
          {source?.kind === 'ics' ? (
            <p className="text-sm text-warn">
              Buổi này thuộc nguồn nhập từ file — sửa tay sẽ mất khi nhập lại.
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 gap-1">
          <Button
            size="icon-lg"
            variant="ghost"
            aria-label={`Sửa buổi ${event.title}`}
            onClick={() => openEditEvent(event)}
          >
            <Edit3 />
          </Button>
          <Button
            size="icon-lg"
            variant="ghost"
            aria-label={`Xoá buổi ${event.title}`}
            onClick={() => setConfirm({ kind: 'event', event })}
          >
            <Trash2 />
          </Button>
        </div>
      </div>
    </Card>
  )
})

export function CalendarScreen() {
  const queryClient = useQueryClient()
  const readControl = useDomainReadControl(['calendar'], false)
  const [view, setView] = useState<'grid' | 'list'>(() => {
    try {
      return window.localStorage.getItem(VIEW_KEY) === 'list' ? 'list' : 'grid'
    } catch {
      return 'grid'
    }
  })
  const [rangeStart, setRangeStart] = useState(todayInVietnam)
  const [sourceDialogOpen, setSourceDialogOpen] = useState(false)
  const [sourceKind, setSourceKind] = useState<'ics' | 'manual'>('ics')
  const [pickedFile, setPickedFile] = useState<File | null>(null)
  const [sourceName, setSourceName] = useState('')
  const [sourceError, setSourceError] = useState<string | null>(null)
  const [sourceConflict, setSourceConflict] = useState<ReturnType<typeof importConflict>>(null)
  const [importReport, setImportReport] = useState<ImportReport | null>(null)
  const [importPending, setImportPending] = useState(false)
  const importRequestRef = useRef<ImportRequestReceipt | null>(null)
  const [confirm, setConfirm] = useState<ConfirmState>(null)
  const [editingSource, setEditingSource] = useState<CalendarSource | null>(null)
  const [eventDialogOpen, setEventDialogOpen] = useState(false)
  const [editingEvent, setEditingEvent] = useState<CalendarEvent | undefined>()
  const [eventError, setEventError] = useState<string | null>(null)

  useEffect(() => {
    const onAcknowledged = (event: Event) => {
      const detail = (event as CustomEvent<{ row: OutboxRow; response: unknown }>).detail
      const request = importRequestRef.current
      if (!detail?.row || !request || !matchesImportAcknowledgement(request, detail.row)) return
      request.acknowledged = true
      request.acknowledgedResponse = detail.response
      const report = validateImportReport(detail.response)
      setImportPending(false)
      if (report) {
        setSourceError(null)
        setImportReport(report)
      } else {
        setImportReport(null)
        setSourceError('Máy chủ đã hoàn tất nhập lịch nhưng báo cáo trả về không hợp lệ.')
      }
    }
    window.addEventListener('microsched:outbox-acknowledged', onAcknowledged)
    return () => window.removeEventListener('microsched:outbox-acknowledged', onAcknowledged)
  }, [])

  const sources = useQuery({
    queryKey: ['calendar', 'sources'],
    queryFn: ({ signal }) => getSources(signal),
    ...CALENDAR_QUERY_OPTIONS,
    ...readControl,
  })
  const events = useQuery({
    queryKey: ['calendar', 'events', rangeStart],
    queryFn: ({ signal }) => getEvents(rangeStart, signal),
    ...CALENDAR_QUERY_OPTIONS,
    ...readControl,
  })
  const manualSources = useMemo(
    () => (sources.data?.items ?? []).filter((source) => source.kind === 'manual'),
    [sources.data?.items],
  )
  const sourceById = useMemo(
    () => new Map((sources.data?.items ?? []).map((source) => [source.id, source])),
    [sources.data?.items],
  )

  const importFile = useMutation({
    mutationFn: async ({ sourceId, file, startedAt }: { sourceId: string; file: File; startedAt: number }) => {
      if (importRequestRef.current?.startedAt !== startedAt) throw new Error('Yêu cầu nhập lịch đã được thay thế.')
      const problem = validateFile(file)
      if (problem) throw new Error(problem)
      return queuedRequest<ImportReport | null>(queryClient, 'calendar.import', {
        path: `/api/calendar/sources/${sourceId}/import`,
        body: { filename: file.name, content: await file.text() }, entityId: sourceId, parentId: sourceId,
      }, { timeoutMs: 60_000 })
    },
    onMutate: ({ sourceId, startedAt }) => {
      // Bind the expected source before mutationFn/file.text()/queue can yield.
      importRequestRef.current = { sourceId, startedAt, acknowledged: false }
      setImportReport(null)
      setImportPending(false)
    },
    onSuccess: (report, { sourceId, startedAt }) => {
      if (importRequestRef.current?.sourceId !== sourceId || importRequestRef.current.startedAt !== startedAt) return
      setSourceError(null)
      const actualReport = validateImportReport(report) ??
        validateImportReport(importRequestRef.current?.acknowledgedResponse)
      if (actualReport) {
        setImportReport(actualReport)
        setImportPending(false)
        return
      }
      if (importRequestRef.current?.acknowledged) {
        setImportReport(null)
        setImportPending(false)
        setSourceError('Máy chủ đã hoàn tất nhập lịch nhưng báo cáo trả về không hợp lệ.')
        return
      }
      if (report === null) {
        setImportPending(true)
        return
      }
      setImportReport(null)
      setImportPending(false)
      setSourceError('Máy chủ trả về báo cáo nhập lịch không hợp lệ.')
    },
    onError: (error) => setSourceError(importErrorMessage(error)),
  })

  const createSource = useMutation({
    mutationFn: (value: { id: string; name: string; kind: 'ics' | 'manual'; color: string }) =>
      queuedRequest<CalendarSource>(queryClient, 'calendar_source.create', { path: '/api/calendar/sources', body: value, entityId: value.id }),
    onSuccess: (source) => {
      setSourceDialogOpen(false)
      setSourceError(null)
      setSourceConflict(null)
      if (sourceKind === 'ics' && pickedFile) {
        importFile.mutate({ sourceId: source.id, file: pickedFile, startedAt: Date.now() })
      }
    },
    onError: (error) => {
      const conflict = importConflict(error)
      if (conflict) setSourceConflict(conflict)
      else setSourceError(importErrorMessage(error))
    },
  })

  const updateSource = useMutation({
    mutationFn: ({
      sourceId,
      isVisible,
      name,
      color,
    }: {
      sourceId: string
      isVisible?: boolean
      name?: string
      color?: string | null
    }) => {
      const body: Record<string, unknown> = {}
      if (isVisible !== undefined) body.is_visible = isVisible
      if (name !== undefined) body.name = name
      if (color !== undefined) body.color = color
      return queuedRequest<CalendarSource>(queryClient, 'calendar_source.update', { path: `/api/calendar/sources/${sourceId}`, body: body as unknown as Json, entityId: sourceId })
    },
    onSuccess: () => {
      setEditingSource(null)
    },
    onError: (error) => setSourceError(importErrorMessage(error)),
  })

  const deleteSource = useMutation({
    mutationFn: (sourceId: string) => queuedRequest<void>(queryClient, 'calendar_source.delete', { path: `/api/calendar/sources/${sourceId}`, entityId: sourceId }),
    onSuccess: () => {
      setConfirm(null)
    },
    onError: (error) => setSourceError(importErrorMessage(error)),
  })

  const createEvent = useMutation({
    mutationFn: (value: Record<string, unknown> & { id: string }) =>
      queuedRequest<CalendarEvent>(queryClient, 'calendar_event.create', { path: '/api/calendar/events', body: value as unknown as Json, entityId: value.id, parentId: typeof value.source_id === 'string' ? value.source_id : null }),
    onSuccess: () => {
      setEventDialogOpen(false)
    },
    onError: (error) => setEventError(importErrorMessage(error)),
  })

  const updateEvent = useMutation({
    mutationFn: ({ eventId, value }: { eventId: string; value: Record<string, unknown> }) =>
      queuedRequest<CalendarEvent>(queryClient, 'calendar_event.update', { path: `/api/calendar/events/${eventId}`, body: value as unknown as Json, entityId: eventId }),
    onSuccess: () => {
      setEventDialogOpen(false)
      setEditingEvent(undefined)
    },
    onError: (error) => setEventError(importErrorMessage(error)),
  })

  const deleteEvent = useMutation({
    mutationFn: (eventId: string) => queuedRequest<void>(queryClient, 'calendar_event.delete', { path: `/api/calendar/events/${eventId}`, entityId: eventId }),
    onSuccess: () => {
      setConfirm(null)
    },
    onError: (error) => setSourceError(importErrorMessage(error)),
  })

  const groupedEvents = groupEvents(events.data?.items ?? [])
  const mutationError = [
    sources.error,
    events.error,
    importFile.error,
    createSource.error,
    updateSource.error,
    deleteSource.error,
    createEvent.error,
    updateEvent.error,
    deleteEvent.error,
  ].find(Boolean)
  const eventDialogError = eventDialogErrorMessage(eventError, createEvent.error ?? updateEvent.error)

  function openSourceDialog(kind: 'ics' | 'manual') {
    setSourceKind(kind)
    setPickedFile(null)
    setSourceName('')
    setSourceError(null)
    setSourceConflict(null)
    setSourceDialogOpen(true)
  }

  function chooseFile(file: File) {
    const problem = validateFile(file)
    if (problem) {
      setSourceError(problem)
      return
    }
    setPickedFile(file)
    setSourceName(fileBaseName(file))
    setSourceError(null)
  }

  function submitSource(value: { name: string; color: string }) {
    if (sourceKind === 'ics' && !pickedFile) {
      setSourceError('Chọn file .ics trước khi tạo nguồn.')
      return
    }
    setSourceName(value.name)
    createSource.mutate({ id: uuidv7(), name: value.name, color: value.color, kind: sourceKind })
  }

  const openNewEvent = useCallback(() => {
    setEditingEvent(undefined)
    setEventError(null)
    setEventDialogOpen(true)
  }, [])

  const openEditEvent = useCallback((event: CalendarEvent) => {
    setEditingEvent(event)
    setEventError(null)
    setEventDialogOpen(true)
  }, [])

  function chooseView(next: 'grid' | 'list') {
    setView(next)
    try {
      window.localStorage.setItem(VIEW_KEY, next)
    } catch {
      // Storage bị chặn (private mode) không được làm hỏng việc chuyển view.
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-extrabold tracking-tight">Lịch</h2>
          <p className="text-sm text-muted-foreground">
            {view === 'grid'
              ? 'Lịch cuộn theo tháng, tuần bắt đầu Thứ Hai.'
              : 'Danh sách 30 ngày theo giờ Việt Nam.'}
          </p>
        </div>
        <div className="flex gap-1 rounded-lg bg-muted p-1" role="group" aria-label="Chế độ xem lịch">
          <Button
            data-testid="calendar-view-toggle-grid"
            size="sm"
            variant={view === 'grid' ? 'secondary' : 'ghost'}
            aria-pressed={view === 'grid'}
            onClick={() => chooseView('grid')}
          >
            Lịch
          </Button>
          <Button
            data-testid="calendar-view-toggle-list"
            size="sm"
            variant={view === 'list' ? 'secondary' : 'ghost'}
            aria-pressed={view === 'list'}
            onClick={() => chooseView('list')}
          >
            Danh sách
          </Button>
        </div>
      </div>

      {view === 'grid' ? <CalendarScrollView /> : (
        <div className="space-y-5">
          {sourceError || mutationError ? (
        <p className="text-sm text-bad" role="alert">
          {sourceError ?? importErrorMessage(mutationError)}
        </p>
          ) : null}

          {importPending ? (
            <p data-testid="calendar-import-pending" role="status" className="text-sm text-muted-foreground">
              Tệp đã lưu trong hàng đợi. Báo cáo số buổi chỉ xuất hiện sau khi máy chủ hoàn tất import.
            </p>
          ) : null}

          {importReport ? (
        <Card data-testid="calendar-import-report" className="gap-2 bg-ok-bg p-4 shadow-1 ring-0">
          <p className="text-sm font-bold">
            Đã nhập {importReport.inserted} buổi · bỏ qua {importReport.skipped.length} · trùng{' '}
            {importReport.duplicates} · thay cho {importReport.removed} buổi cũ
          </p>
          <p className="text-sm text-muted-foreground">
            Nếu request bị timeout, thử lại an toàn vì import luôn thay sạch nguồn.
          </p>
          {importReport.skipped.length > 0 ? (
            <details className="text-sm">
              <summary className="cursor-pointer font-semibold">Xem lý do bỏ qua</summary>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {importReport.skipped.slice(0, 5).map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </Card>
          ) : null}

          <section aria-labelledby="calendar-sources-heading" className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 id="calendar-sources-heading" className="text-base font-bold">
                Nguồn lịch
              </h3>
              <div className="flex flex-wrap gap-2">
                <Button
                  data-testid="calendar-manual-source-button"
                  size="lg"
                  variant="outline"
                  onClick={() => openSourceDialog('manual')}
                >
                  <Plus data-icon="inline-start" />
                  Nguồn thủ công
                </Button>
                <Button size="lg" onClick={() => openSourceDialog('ics')}>
                  <CalendarDays data-icon="inline-start" />
                  Thêm nguồn lịch
                </Button>
              </div>
            </div>
        {sources.isPending ? <p className="text-sm text-muted-foreground">Đang tải nguồn lịch…</p> : null}
        <div className="space-y-2">
          {(sources.data?.items ?? []).map((source) => (
            <Card
              data-testid="calendar-source-row"
              data-source-id={source.id}
              key={source.id}
              className="gap-3 p-4 shadow-1 ring-0"
            >
              <div className="flex flex-wrap items-center gap-3">
                <span
                  aria-hidden="true"
                  className="size-4 shrink-0 rounded-full ring-2 ring-border"
                  style={{ backgroundColor: sourceColorToken(source.color) }}
                />
                <div className="min-w-0 flex-1">
                  <p className="break-words text-base font-bold">{source.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {source.event_count} buổi · {source.kind === 'manual' ? 'thủ công' : 'nhập từ file'}
                  </p>
                </div>
                <label className="flex min-h-11 items-center gap-2 text-sm font-semibold">
                  <Checkbox
                    data-testid="calendar-source-toggle"
                    className="size-5 rounded-md"
                    checked={source.is_visible}
                    aria-label={`Hiện nguồn ${source.name}`}
                    onCheckedChange={(checked) =>
                      updateSource.mutate({ sourceId: source.id, isVisible: checked === true })
                    }
                  />
                  <span>Hiện</span>
                </label>
                {source.kind === 'ics' ? (
                  <FilePicker
                    testId="calendar-import-button"
                    label="Nhập lại"
                    accept=".ics,text/calendar"
                    disabled={importFile.isPending}
                    onPick={(file) => importFile.mutate({ sourceId: source.id, file, startedAt: Date.now() })}
                  />
                ) : null}
                <Button
                  data-testid="calendar-source-edit"
                  size="icon-lg"
                  variant="ghost"
                  aria-label={`Sửa nguồn ${source.name}`}
                  onClick={() => setEditingSource(source)}
                >
                  <Edit3 />
                </Button>
                <Button
                  data-testid="calendar-source-delete"
                  size="icon-lg"
                  variant="ghost"
                  aria-label={`Xoá nguồn ${source.name}`}
                  onClick={() => setConfirm({ kind: 'source', source })}
                >
                  <Trash2 />
                </Button>
              </div>
            </Card>
          ))}
        </div>
          </section>

          <section aria-labelledby="calendar-events-heading" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 id="calendar-events-heading" className="text-base font-bold">
            Buổi trong khoảng này
          </h3>
          <div className="flex gap-2">
            <Button
              data-testid="calendar-range-prev"
              size="icon-lg"
              variant="outline"
              aria-label="Khoảng trước"
              onClick={() => setRangeStart((day) => addVietnamDays(day, -30))}
            >
              <ChevronLeft />
            </Button>
            <Button
              data-testid="calendar-range-next"
              size="icon-lg"
              variant="outline"
              aria-label="Khoảng sau"
              onClick={() => setRangeStart((day) => addVietnamDays(day, 30))}
            >
              <ChevronRight />
            </Button>
            {manualSources.length > 0 ? (
              <Button size="lg" onClick={openNewEvent}>
                <Plus data-icon="inline-start" />
                Thêm buổi
              </Button>
            ) : null}
          </div>
        </div>
        {events.isPending ? <p className="text-sm text-muted-foreground">Đang tải buổi…</p> : null}
        {events.data && groupedEvents.length === 0 ? (
          <Card className="rounded-lg border border-dashed bg-transparent p-6 text-center text-sm text-muted-foreground shadow-none">
            Chưa có buổi trong khoảng này.
          </Card>
        ) : null}
        <div className="space-y-5">
          {groupedEvents.map(([, dayEvents]) => (
            <div key={dayEvents[0].id} className="space-y-2">
              <h4 className="text-sm font-bold capitalize text-muted-foreground">
                {formatVietnamDate(dayEvents[0].starts_at)}
              </h4>
              {dayEvents.map((event) => (
                <EventCard
                  key={event.id}
                  event={event}
                  source={sourceById.get(event.source_id)}
                  openEditEvent={openEditEvent}
                  setConfirm={setConfirm}
                />
              ))}
            </div>
          ))}
        </div>
          </section>
        </div>
      )}

      <Dialog open={sourceDialogOpen} onOpenChange={setSourceDialogOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{sourceKind === 'ics' ? 'Thêm nguồn lịch' : 'Thêm nguồn thủ công'}</DialogTitle>
            <DialogDescription>
              {sourceKind === 'ics' ? 'Chọn file ICS trước khi tạo nguồn.' : 'Nguồn này không nhận import file.'}
            </DialogDescription>
          </DialogHeader>
          {sourceKind === 'ics' ? (
            <div className="space-y-2">
              <FilePicker accept=".ics,text/calendar" onPick={chooseFile} />
              <p className="text-sm text-muted-foreground">
                {pickedFile ? `Đã chọn: ${pickedFile.name}` : 'Chưa chọn file.'}
              </p>
            </div>
          ) : null}
          {sourceConflict ? (
            <div className="space-y-3 rounded-lg bg-warn-bg p-4" role="alert">
              <p className="text-sm">
                {sourceConflict.message}{' '}
                {pickedFile ? 'Nhập đè lên nguồn đó?' : 'Đặt tên khác để tạo nguồn.'}
              </p>
              <div className="flex flex-wrap gap-2">
                {pickedFile ? (
                  <Button
                    size="lg"
                    disabled={importFile.isPending}
                    onClick={() => {
                      setSourceDialogOpen(false)
                      importFile.mutate({ sourceId: sourceConflict.existingSourceId, file: pickedFile, startedAt: Date.now() })
                    }}
                  >
                    Nhập đè
                  </Button>
                ) : null}
                <Button size="lg" variant="outline" onClick={() => setSourceConflict(null)}>
                  Đặt tên khác
                </Button>
              </div>
            </div>
          ) : null}
          {sourceError ? <p className="text-sm text-bad" role="alert">{sourceError}</p> : null}
          <SourceForm
            key={`${sourceKind}-${sourceName}`}
            kind={sourceKind}
            initialName={sourceName}
            pending={createSource.isPending || importFile.isPending}
            onSubmit={submitSource}
            onCancel={() => setSourceDialogOpen(false)}
          />
        </DialogContent>
      </Dialog>

      <Dialog
        open={eventDialogOpen}
        onOpenChange={(open) => {
          setEventDialogOpen(open)
          if (!open) setEditingEvent(undefined)
        }}
      >
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingEvent ? 'Sửa buổi' : 'Tạo buổi thủ công'}</DialogTitle>
            <DialogDescription>Thời gian được hiểu theo giờ Việt Nam (+07:00).</DialogDescription>
          </DialogHeader>
          {editingEvent && sourceById.get(editingEvent.source_id)?.kind === 'ics' ? (
            <p className="text-sm text-warn">
              Buổi này thuộc nguồn nhập từ file — sửa tay sẽ mất khi nhập lại.
            </p>
          ) : null}
          {eventDialogError ? (
            <p data-testid="calendar-event-error" className="text-sm text-bad" role="alert">
              {eventDialogError}
            </p>
          ) : null}
          <EventForm
            initial={editingEvent}
            manualSources={manualSources}
            pending={createEvent.isPending || updateEvent.isPending}
            onSubmit={(value) => {
              if (editingEvent) {
                updateEvent.mutate({ eventId: editingEvent.id, value })
              } else {
                createEvent.mutate({ ...value, id: uuidv7() })
              }
            }}
            onCancel={() => setEventDialogOpen(false)}
          />
        </DialogContent>
      </Dialog>

      <Dialog open={confirm !== null} onOpenChange={(open) => !open && setConfirm(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{confirm?.kind === 'source' ? 'Xoá nguồn lịch?' : 'Xoá buổi?'}</DialogTitle>
            <DialogDescription>
              {confirm?.kind === 'source'
                ? `Xoá nguồn “${confirm.source.name}” và ${confirm.source.event_count} buổi của nó? Không hoàn tác được.`
                : `Xoá buổi “${confirm && confirm.kind === 'event' ? confirm.event.title : ''}”? Không hoàn tác được.`}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-wrap gap-2">
            <Button
              size="lg"
              variant="destructive"
              disabled={deleteSource.isPending || deleteEvent.isPending}
              onClick={() => {
                if (!confirm) return
                if (confirm.kind === 'source') deleteSource.mutate(confirm.source.id)
                else deleteEvent.mutate(confirm.event.id)
              }}
            >
              {deleteSource.isPending || deleteEvent.isPending ? 'Đang xoá…' : 'Xoá'}
            </Button>
            <Button size="lg" variant="outline" onClick={() => setConfirm(null)}>
              Huỷ
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={editingSource !== null}
        onOpenChange={(open) => !open && setEditingSource(null)}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Sửa nguồn lịch</DialogTitle>
            <DialogDescription>
              Đổi tên và màu nhận diện của nguồn lịch này.
            </DialogDescription>
          </DialogHeader>
          {editingSource ? (
            <SourceForm
              kind={editingSource.kind === 'ics' ? 'ics' : 'manual'}
              initialName={editingSource.name}
              initialColor={editingSource.color}
              submitLabel="Lưu thay đổi"
              pending={updateSource.isPending}
              onSubmit={({ name, color }) =>
                updateSource.mutate({ sourceId: editingSource.id, name, color })
              }
              onCancel={() => setEditingSource(null)}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  )
}
