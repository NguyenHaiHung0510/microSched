import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Archive,
  Clock,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react'
import { toast } from 'sonner'

import { apiRequest } from '@/api'
import { VIETNAM_TIME_ZONE, vietnamInputToIso } from '@/calendar-ui'
import { navigate } from '@/lib/route'
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
import { Input } from '@/components/ui/input'
import { CaptureGrid } from '@/CaptureGrid'
import { DashboardPanel } from '@/DashboardPanel'
import { EntryEditDialog, type EntryEditPayload } from '@/EntryEditDialog'
import { GroupForm } from '@/GroupForm'
import { TrackerForm, type TrackerWritePayload } from '@/TrackerForm'
import {
  subscriptionQueryKey,
  type SettingsItem,
  type Subscription,
} from '@/subscription-ui'
import { errorMessage } from '@/tracker-undo'
import { ensurePushSubscription } from '@/push-subscription'
import {
  backdateOptions,
  capturePayload,
  currentVietnamMonth,
  formatQuantity,
  formatVnd,
  sortTrackersForGrid,
  trackerInvalidationKey,
  trackerQueryKey,
  useTrackerWrites,
  type DashboardResponse,
  type Entry,
  type Tracker,
  type TrackerGroup,
} from '@/tracker-ui'

const UNLOCK_MS = 1500

type BackdateChoice = 'yesterday' | '2h' | 'custom'

function monthLabel(month: string): string {
  const [year, monthNum] = month.split('-').map(Number)
  return new Intl.DateTimeFormat('vi-VN', { month: 'long', year: 'numeric' }).format(
    new Date(year, monthNum - 1, 1),
  )
}

function formatEntryLine(entry: Entry): string {
  if (entry.amount != null) return `${entry.amount.toLocaleString('vi-VN')} ₫`
  if (entry.quantity != null) return formatQuantity(entry.quantity)
  return 'Đã ghi'
}

export function TrackerScreen({ privateUnlocked }: { privateUnlocked: boolean }) {
  const queryClient = useQueryClient()
  const refresh = () => void queryClient.invalidateQueries({ queryKey: trackerInvalidationKey })
  const writes = useTrackerWrites(refresh)
  const month = currentVietnamMonth()
  const wasUnlocked = useRef(privateUnlocked)

  const groupsQuery = useQuery({
    queryKey: trackerQueryKey('groups'),
    queryFn: () => apiRequest<{ items: TrackerGroup[] }>('/api/tracker/groups'),
  })
  const trackersQuery = useQuery({
    queryKey: trackerQueryKey('trackers'),
    queryFn: () => apiRequest<{ items: Tracker[] }>('/api/tracker/trackers'),
  })
  const dashboardQuery = useQuery({
    queryKey: [...trackerQueryKey('dashboard'), month],
    queryFn: () => apiRequest<DashboardResponse>(`/api/tracker/dashboard?month=${month}`),
  })
  const entriesQuery = useQuery({
    queryKey: trackerQueryKey('entries'),
    queryFn: () => apiRequest<{ items: Entry[] }>('/api/tracker/entries?limit=20'),
  })
  const subscriptionsQuery = useQuery({
    queryKey: subscriptionQueryKey('subscriptions'),
    queryFn: () => apiRequest<{ items: Subscription[] }>('/api/subscriptions'),
  })
  const settingsQuery = useQuery({
    queryKey: subscriptionQueryKey('settings'),
    queryFn: () => apiRequest<{ items: SettingsItem[] }>('/api/settings'),
  })

  const trackers = trackersQuery.data?.items ?? []
  const groups = groupsQuery.data?.items ?? []

  // C1: the private gate lives in PrivateGate (shared with other screens); the
  // tracker query family is this screen's own cache, so IT must react to the
  // lock/unlock transition. On lock, cached tracker names / entries / dashboard
  // numbers are erased BEFORE any refetch can paint the previous result while
  // the request is pending (same R6 order PrivateGate uses for tasks). On
  // unlock, the queries refetch so private rows come back.
  useEffect(() => {
    const previous = wasUnlocked.current
    if (previous && !privateUnlocked) {
      queryClient.removeQueries({ queryKey: trackerInvalidationKey })
      void queryClient.invalidateQueries({ queryKey: trackerInvalidationKey })
    } else if (!previous && privateUnlocked) {
      void queryClient.invalidateQueries({ queryKey: trackerInvalidationKey })
    }
    wasUnlocked.current = privateUnlocked
  }, [privateUnlocked, queryClient])

  // §5.2: order is computed once per membership change and then frozen — a capture
  // must never re-sort the grid under the finger.
  const membershipKey = trackers.map((tracker) => tracker.id).sort().join(',')
  const frozenIds = useMemo(
    () => sortTrackersForGrid(trackers).map((tracker) => tracker.id),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [membershipKey],
  )
  // Map the frozen id order against the LATEST tracker rows so last_entry_at /
  // entry_count_30d are live — a capture then shows "Vừa xong" immediately
  // instead of waiting for the refetch to land a fresh row.
  const trackerMap = new Map(trackers.map((tracker) => [tracker.id, tracker]))
  const frozenOrder = frozenIds
    .map((id) => trackerMap.get(id))
    .filter((tracker): tracker is Tracker => Boolean(tracker))

  const [createOpen, setCreateOpen] = useState(false)
  const [editingTracker, setEditingTracker] = useState<Tracker | null>(null)
  const [groupOpen, setGroupOpen] = useState(false)
  const [editingGroup, setEditingGroup] = useState<TrackerGroup | null>(null)
  const [deletingGroup, setDeletingGroup] = useState<TrackerGroup | null>(null)
  const [backdateFor, setBackdateFor] = useState<Tracker | null>(null)
  const [backdateChoice, setBackdateChoice] = useState<BackdateChoice>('yesterday')
  const [backdateCustom, setBackdateCustom] = useState('')
  const [archiveFor, setArchiveFor] = useState<Tracker | null>(null)
  const [editingEntry, setEditingEntry] = useState<Entry | null>(null)
  const [lockedIds, setLockedIds] = useState<ReadonlySet<string>>(new Set())
  const [capturingIds, setCapturingIds] = useState<ReadonlySet<string>>(new Set())
  const unlockTimers = useRef<Map<string, number>>(new Map())

  useEffect(() => {
    const timers = unlockTimers.current
    return () => {
      for (const timer of timers.values()) window.clearTimeout(timer)
      timers.clear()
    }
  }, [])

  function lock(trackerId: string) {
    setLockedIds((previous) => {
      const next = new Set(previous)
      next.add(trackerId)
      return next
    })
  }

  function unlockLater(trackerId: string) {
    const existing = unlockTimers.current.get(trackerId)
    if (existing) window.clearTimeout(existing)
    const timer = window.setTimeout(() => {
      unlockTimers.current.delete(trackerId)
      setLockedIds((previous) => {
        const next = new Set(previous)
        next.delete(trackerId)
        return next
      })
    }, UNLOCK_MS)
    unlockTimers.current.set(trackerId, timer)
  }

  function capture(tracker: Tracker, input?: string, occurredAt?: string) {
    if (lockedIds.has(tracker.id)) return
    lock(tracker.id)
    setCapturingIds((previous) => {
      const next = new Set(previous)
      next.add(tracker.id)
      return next
    })
    writes.createEntry.mutate(
      capturePayload(tracker, input ?? '', occurredAt),
      {
        onSuccess: (entry) => {
          setCapturingIds((previous) => {
            const next = new Set(previous)
            next.delete(tracker.id)
            return next
          })
          toast(
            <span className="block min-w-0 max-w-full break-words">
              Đã ghi “{tracker.name}”
            </span>,
            {
              duration: 10_000,
              action: {
                label: 'Hoàn tác',
                onClick: () => undoDeleteEntry(entry.id),
              },
            },
          )
        },
        onError: (error) => {
          setCapturingIds((previous) => {
            const next = new Set(previous)
            next.delete(tracker.id)
            return next
          })
          toast.error(errorMessage(error))
        },
        onSettled: () => unlockLater(tracker.id),
      },
    )
  }

  function submitBackdate() {
    if (!backdateFor) return
    const option =
      backdateChoice === 'custom'
        ? backdateCustom
          ? vietnamInputToIso(backdateCustom)
          : undefined
        : backdateOptions().find(({ label }) =>
            backdateChoice === 'yesterday' ? label === 'Hôm qua' : label === '2 giờ trước',
          )?.value
    capture(backdateFor, undefined, option)
    setBackdateFor(null)
  }

  function submitTracker(payload: TrackerWritePayload) {
    if (editingTracker) {
      const { register_push: registerPush, ...trackerPayload } = payload
      const saveTracker = () =>
        writes.updateTracker.mutate(
          { trackerId: editingTracker.id, payload: trackerPayload },
          {
            onSuccess: () => setEditingTracker(null),
            onError: (error) => toast.error(errorMessage(error)),
          },
        )
      if (registerPush) {
        void ensurePushSubscription()
          .then(saveTracker)
          .catch((error: unknown) =>
            toast.error(error instanceof Error ? error.message : errorMessage(error)),
          )
      } else {
        saveTracker()
      }
      return
    }
    writes.createTracker.mutate(payload, {
      onSuccess: () => setCreateOpen(false),
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  function submitEntry(entryId: string, payload: EntryEditPayload) {
    writes.updateEntry.mutate(
      { entryId, payload },
      {
        onSuccess: () => setEditingEntry(null),
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  function removeEntry(entry: Entry) {
    writes.deleteEntry.mutate(entry.id, {
      onSuccess: () => {
        toast(<span>Đã xoá bản ghi</span>, {
          duration: 10_000,
          action: { label: 'Hoàn tác', onClick: () => undoRestoreEntry(entry.id) },
        })
      },
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  // M4: an undo/restore failure must be visible and retryable — the toast action
  // disappearing silently would make the user believe the delete was undone.
  function undoDeleteEntry(entryId: string) {
    writes.deleteEntry.mutate(entryId, {
      onError: (error) => {
        toast.error('Không hoàn tác được bản ghi', {
          description: errorMessage(error),
          action: { label: 'Thử lại', onClick: () => undoDeleteEntry(entryId) },
        })
      },
    })
  }

  function undoRestoreEntry(entryId: string) {
    writes.restoreEntry.mutate(entryId, {
      onError: (error) => {
        toast.error('Không khôi phục được bản ghi', {
          description: errorMessage(error),
          action: { label: 'Thử lại', onClick: () => undoRestoreEntry(entryId) },
        })
      },
    })
  }

  function undoRestoreTracker(trackerId: string) {
    writes.restoreTracker.mutate(trackerId, {
      onError: (error) => {
        toast.error('Không khôi phục được tracker', {
          description: errorMessage(error),
          action: { label: 'Thử lại', onClick: () => undoRestoreTracker(trackerId) },
        })
      },
    })
  }

  // Tracker/dashboard errors render inside their own panels (M3); this card
  // covers the remaining shared queries only.
  const queryError =
    groupsQuery.error ??
    entriesQuery.error ??
    subscriptionsQuery.error ??
    settingsQuery.error
  const showListPrice =
    settingsQuery.data?.items.find((item) => item.key === 'show_list_price')?.value !== false
  const pendingForm = writes.createTracker.isPending || writes.updateTracker.isPending
  const pendingGroup = writes.createGroup.isPending || writes.updateGroup.isPending
  const entryTracker = editingEntry
    ? trackers.find((tracker) => tracker.id === editingEntry?.tracker_id) ?? null
    : null

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-extrabold text-primary">Theo dõi</h2>
          <p className="text-sm text-muted-foreground">
            Bấm để ghi, giữ để ghi lùi giờ, hoàn tác trong 10 giây.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="lg" variant="outline" className="min-h-11" onClick={() => setGroupOpen(true)}>
            <Plus data-icon="inline-start" />
            Nhóm mới
          </Button>
          <Button size="lg" className="min-h-11" onClick={() => setCreateOpen(true)}>
            <Plus data-icon="inline-start" />
            Tracker mới
          </Button>
        </div>
      </div>

      {queryError ? (
        <Card className="gap-3 p-4 shadow-1 ring-0" role="alert">
          <p className="text-sm text-bad">Không tải được dữ liệu tracker.</p>
          <Button variant="outline" size="lg" className="min-h-11" onClick={() => void refresh()}>
            <RefreshCw data-icon="inline-start" />
            Thử lại
          </Button>
        </Card>
      ) : null}

      <Card className="gap-3 p-4 shadow-1 ring-0">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0">
            <h3 className="text-base font-bold">Đăng ký định kỳ</h3>
            <p className="text-sm text-muted-foreground">Theo dõi hạn và chi phí cố định.</p>
          </div>
          <Button
            data-testid="subscription-entry"
            size="lg"
            variant="outline"
            className="min-h-11"
            onClick={() => navigate('/subscription')}
          >
            Đăng ký · {subscriptionsQuery.data?.items.length ?? 0} khoản
          </Button>
        </div>
      </Card>

      <CaptureGrid
        trackers={frozenOrder}
        locked={lockedIds}
        pendingTrackerId={capturingIds.size === 1 ? [...capturingIds][0] : null}
        loading={trackersQuery.isPending}
        error={trackersQuery.error}
        onRetry={() => void refresh()}
        onCapture={capture}
        onBackdate={(tracker) => {
          setBackdateChoice('yesterday')
          setBackdateCustom('')
          setBackdateFor(tracker)
        }}
      />

      <DashboardPanel
        dashboard={dashboardQuery.data ?? null}
        monthLabel={monthLabel(month)}
        trackers={trackers}
        loading={dashboardQuery.isPending}
        error={dashboardQuery.error}
        // TanStack v5 returns 0 (not null) while the query has never
        // succeeded; fold that into null so the chip reads "never fresh"
        // instead of a ~57-year-old elapsed time.
        lastSuccessAt={dashboardQuery.dataUpdatedAt || null}
        queryStatus={dashboardQuery.status}
        onRetry={() => void refresh()}
      />

      <Card className="gap-3 p-4 shadow-1 ring-0">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="text-base font-bold">Bản ghi gần đây</h3>
          <span className="text-xs text-muted-foreground">20 bản ghi mới nhất</span>
        </div>
        {entriesQuery.data?.items.length ? (
          <div className="space-y-2">
            {entriesQuery.data.items.map((entry) => {
              const tracker = trackers.find((item) => item.id === entry.tracker_id)
              return (
                <div
                  key={entry.id}
                  data-testid="entry-row"
                  data-entry-id={entry.id}
                  className="flex items-center justify-between gap-3 rounded-lg bg-muted/50 p-3"
                >
                  <div className="min-w-0">
                    <p className="max-w-full break-words text-sm font-semibold">
                      {tracker?.name ?? 'Đã archive'}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {entry.occurred_at
                        ? new Intl.DateTimeFormat('vi-VN', {
                            timeZone: VIETNAM_TIME_ZONE,
                            day: '2-digit',
                            month: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit',
                          }).format(new Date(entry.occurred_at))
                        : ''}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold tabular-nums">
                      {showListPrice &&
                      entry.list_amount != null &&
                      entry.amount != null &&
                      entry.list_amount !== entry.amount ? (
                        <span className="mr-2 text-xs font-normal text-muted-foreground line-through">
                          {formatVnd(entry.list_amount)}
                        </span>
                      ) : null}
                      {formatEntryLine(entry)}
                    </span>
                    <Button
                      data-testid="entry-edit"
                      data-entry-id={entry.id}
                      variant="ghost"
                      size="icon-lg"
                      className="size-11"
                      aria-label="Sửa bản ghi"
                      onClick={() => setEditingEntry(entry)}
                    >
                      <Pencil />
                    </Button>
                    <Button
                      data-testid="entry-undo"
                      data-entry-id={entry.id}
                      variant="ghost"
                      size="icon-lg"
                      className="size-11"
                      aria-label="Xoá bản ghi"
                      onClick={() => removeEntry(entry)}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Chưa có bản ghi nào.</p>
        )}
      </Card>

      <Card className="gap-3 p-4 shadow-1 ring-0">
        <h3 className="text-base font-bold">Quản lý tracker</h3>
        {trackers.length ? (
          <div className="space-y-2">
            {trackers.map((tracker) => (
              <div
                key={tracker.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-muted/50 p-3"
              >
                <div className="min-w-0">
                  <p className="max-w-full break-words text-sm font-semibold">{tracker.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {tracker.input_mode === 'event'
                      ? 'Một chạm'
                      : tracker.input_mode === 'money'
                        ? 'Số tiền'
                        : `Số lượng (${tracker.unit ?? 'đơn vị'})`}
                    {tracker.group_id
                      ? ` · ${groups.find((group) => group.id === tracker.group_id)?.name ?? ''}`
                      : ''}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-1.5 text-xs font-semibold">
                    <Checkbox
                      data-testid="tracker-private-toggle"
                      data-tracker-id={tracker.id}
                      className="size-4 rounded-[4px]"
                      checked={tracker.is_private}
                      disabled={!tracker.is_private && !privateUnlocked}
                      onCheckedChange={(checked) =>
                        writes.updateTracker.mutate(
                          { trackerId: tracker.id, payload: { is_private: checked === true } },
                          { onError: (error) => toast.error(errorMessage(error)) },
                        )
                      }
                    />
                    Riêng tư
                  </label>
                  <Button
                    variant="ghost"
                    size="icon-lg"
                    className="size-11"
                    aria-label={`Sửa ${tracker.name}`}
                    onClick={() => setEditingTracker(tracker)}
                  >
                    <Pencil />
                  </Button>
                  <Button
                    data-testid="tracker-archive"
                    data-tracker-id={tracker.id}
                    variant="ghost"
                    size="icon-lg"
                    className="size-11"
                    aria-label={`Lưu trữ ${tracker.name}`}
                    onClick={() => setArchiveFor(tracker)}
                  >
                    <Archive />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Chưa có tracker nào.</p>
        )}
      </Card>

      <Card className="gap-3 p-4 shadow-1 ring-0">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-base font-bold">Quản lý nhóm</h3>
          <Button
            variant="ghost"
            size="sm"
            className="min-h-11"
            aria-label="Thêm nhóm"
            onClick={() => setGroupOpen(true)}
          >
            <Plus data-icon="inline-start" />
            Thêm
          </Button>
        </div>
        {groups.length ? (
          <div className="space-y-2">
            {groups.map((group) => (
              <div
                key={group.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-muted/50 p-3"
              >
                <div className="min-w-0">
                  <p className="max-w-full break-words text-sm font-semibold">{group.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {group.kind === 'health' ? 'Sức khoẻ' : 'Tài chính'} · {group.tracker_count}{' '}
                    tracker
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="icon-lg"
                    className="size-11"
                    aria-label={`Sửa nhóm ${group.name}`}
                    onClick={() => setEditingGroup(group)}
                  >
                    <Pencil />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-lg"
                    className="size-11"
                    aria-label={`Xoá nhóm ${group.name}`}
                    onClick={() => setDeletingGroup(group)}
                  >
                    <Trash2 />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Chưa có nhóm nào.</p>
        )}
      </Card>

      <Dialog open={createOpen} onOpenChange={(open) => !open && setCreateOpen(false)}>
        <DialogContent data-testid="tracker-dialog">
          <DialogHeader>
            <DialogTitle>Tracker mới</DialogTitle>
            <DialogDescription>Tạo một nút ghi một chạm mới.</DialogDescription>
          </DialogHeader>
          <TrackerForm
            groups={groups}
            pending={pendingForm}
            privateLocked={!privateUnlocked}
            onSubmit={submitTracker}
            onCancel={() => setCreateOpen(false)}
          />
        </DialogContent>
      </Dialog>

      <Dialog open={editingTracker !== null} onOpenChange={(open) => !open && setEditingTracker(null)}>
        <DialogContent data-testid="tracker-dialog">
          <DialogHeader>
            <DialogTitle>Sửa tracker</DialogTitle>
            <DialogDescription>Cập nhật thông tin của tracker này.</DialogDescription>
          </DialogHeader>
          {editingTracker ? (
            <TrackerForm
              initial={editingTracker}
              groups={groups}
              pending={pendingForm}
              privateLocked={!privateUnlocked}
              onSubmit={submitTracker}
              onCancel={() => setEditingTracker(null)}
            />
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog open={groupOpen} onOpenChange={(open) => !open && setGroupOpen(false)}>
        <DialogContent data-testid="group-dialog">
          <DialogHeader>
            <DialogTitle>Nhóm mới</DialogTitle>
            <DialogDescription>Nhóm các tracker cùng loại lại với nhau.</DialogDescription>
          </DialogHeader>
          <GroupForm
            pending={pendingGroup}
            onSubmit={(payload) =>
              writes.createGroup.mutate(payload, {
                onSuccess: () => setGroupOpen(false),
                onError: (error) => toast.error(errorMessage(error)),
              })
            }
            onCancel={() => setGroupOpen(false)}
          />
        </DialogContent>
      </Dialog>

      <Dialog
        open={editingGroup !== null}
        onOpenChange={(open) => !open && setEditingGroup(null)}
      >
        <DialogContent data-testid="group-dialog">
          <DialogHeader>
            <DialogTitle>Sửa nhóm</DialogTitle>
            <DialogDescription>Cập nhật tên nhóm này.</DialogDescription>
          </DialogHeader>
          {editingGroup ? (
            <GroupForm
              initial={editingGroup}
              pending={pendingGroup}
              onSubmit={(payload) =>
                writes.updateGroup.mutate(
                  { groupId: editingGroup.id, payload },
                  {
                    onSuccess: () => setEditingGroup(null),
                    onError: (error) => toast.error(errorMessage(error)),
                  },
                )
              }
              onCancel={() => setEditingGroup(null)}
            />
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog
        open={deletingGroup !== null}
        onOpenChange={(open) => !open && setDeletingGroup(null)}
      >
        <DialogContent data-testid="group-delete-dialog">
          <DialogHeader>
            <DialogTitle>Xoá nhóm?</DialogTitle>
            <DialogDescription>
              {deletingGroup
                ? `“${deletingGroup.name}” sẽ bị xoá. Các tracker trong nhóm được bỏ nhóm lại, không bị xoá.`
                : ''}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="destructive"
              size="lg"
              className="min-h-11"
              onClick={() => {
                if (!deletingGroup) return
                writes.deleteGroup.mutate(deletingGroup.id, {
                  onSuccess: () =>
                    toast(<span>Đã xoá nhóm “{deletingGroup.name}”</span>, { duration: 10_000 }),
                  onError: (error) => toast.error(errorMessage(error)),
                })
                setDeletingGroup(null)
              }}
            >
              Xoá nhóm
            </Button>
            <Button size="lg" variant="outline" className="min-h-11" onClick={() => setDeletingGroup(null)}>
              Huỷ
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={backdateFor !== null}
        onOpenChange={(open) => !open && setBackdateFor(null)}
      >
        <DialogContent data-testid="tracker-backdate-dialog">
          <DialogHeader>
            <DialogTitle>Ghi lùi giờ</DialogTitle>
            <DialogDescription>
              {backdateFor ? `Ghi cho “${backdateFor.name}” vào một thời điểm trước.` : ''}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant={backdateChoice === 'yesterday' ? 'secondary' : 'ghost'}
                className="min-h-11"
                onClick={() => setBackdateChoice('yesterday')}
              >
                Hôm qua
              </Button>
              <Button
                variant={backdateChoice === '2h' ? 'secondary' : 'ghost'}
                className="min-h-11"
                onClick={() => setBackdateChoice('2h')}
              >
                2 giờ trước
              </Button>
            </div>
            <label className="flex items-center gap-2 text-sm font-semibold">
              <Clock className="size-4 text-muted-foreground" />
              <Input
                className="h-10 bg-card"
                type="datetime-local"
                value={backdateCustom}
                onChange={(event) => {
                  setBackdateCustom(event.target.value)
                  if (event.target.value) setBackdateChoice('custom')
                }}
              />
            </label>
            <Button size="lg" className="min-h-11 w-full" onClick={submitBackdate}>
              Ghi
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={archiveFor !== null} onOpenChange={(open) => !open && setArchiveFor(null)}>
        <DialogContent data-testid="tracker-archive-dialog">
          <DialogHeader>
            <DialogTitle>Lưu trữ tracker?</DialogTitle>
            <DialogDescription>
              {archiveFor
                ? `“${archiveFor.name}” sẽ biến mất khỏi lưới ghi, nhưng lịch sử bản ghi vẫn được giữ.`
                : ''}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="destructive"
              size="lg"
              className="min-h-11"
              onClick={() => {
                if (!archiveFor) return
                writes.archiveTracker.mutate(archiveFor.id, {
                  onSuccess: () => {
                    setArchiveFor(null)
                    toast(<span>Đã lưu trữ “{archiveFor.name}”</span>, {
                      duration: 10_000,
                      action: {
                        label: 'Hoàn tác',
                        onClick: () => undoRestoreTracker(archiveFor.id),
                      },
                    })
                  },
                  onError: (error) => toast.error(errorMessage(error)),
                })
              }}
            >
              Lưu trữ
            </Button>
            <Button size="lg" variant="outline" className="min-h-11" onClick={() => setArchiveFor(null)}>
              Huỷ
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {editingEntry ? (
        <EntryEditDialog
          key={editingEntry.id}
          entry={editingEntry}
          tracker={entryTracker}
          pending={writes.updateEntry.isPending}
          onClose={() => {
            // M11: closing the dialog while the PATCH is in flight would discard
            // the user's draft on failure — keep it mounted until it settles.
            if (!writes.updateEntry.isPending) setEditingEntry(null)
          }}
          onSubmit={submitEntry}
        />
      ) : null}
    </div>
  )
}
