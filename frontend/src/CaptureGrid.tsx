import { useState } from 'react'
import { ChevronDown, ChevronUp, Folder, Sparkles } from 'lucide-react'

import { TrackerCard } from '@/TrackerCard'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  groupTrackersByGroup,
  type Tracker,
  type TrackerGroup,
} from '@/tracker-ui'

type CaptureGridProps = {
  trackers: Tracker[]
  groups?: TrackerGroup[]
  locked: ReadonlySet<string>
  pendingTrackerId: string | null
  loading: boolean
  error: unknown
  onRetry: () => void
  onCapture: (tracker: Tracker, input?: string) => void
  onBackdate: (tracker: Tracker) => void
}

export function CaptureGrid({
  trackers,
  groups = [],
  locked,
  pendingTrackerId,
  loading,
  error,
  onRetry,
  onCapture,
  onBackdate,
}: CaptureGridProps) {
  const [collapsedGroups, setCollapsedGroups] = useState<ReadonlySet<string>>(new Set())
  const [unassignedCollapsed, setUnassignedCollapsed] = useState(false)

  // Loading and error are separate from "empty": an empty grid means the server
  // answered with zero trackers, not that the request is still pending (M3).
  if (loading) {
    return (
      <p data-testid="tracker-grid-loading" className="py-6 text-center text-sm text-muted-foreground">
        Đang tải tracker…
      </p>
    )
  }
  if (error) {
    return (
      <Card
        data-testid="tracker-grid-error"
        className="gap-3 p-4 shadow-1 ring-0"
        role="alert"
      >
        <p className="text-sm text-bad">Không tải được lưới ghi.</p>
        <Button variant="outline" size="lg" className="min-h-11" onClick={onRetry}>
          Thử lại
        </Button>
      </Card>
    )
  }
  if (trackers.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        Chưa có tracker nào. Bấm “Tracker mới” để bắt đầu.
      </p>
    )
  }

  const grouped = groupTrackersByGroup(trackers, groups)
  const hasGroupedStructure = grouped.grouped.length > 0

  function toggleGroup(groupId: string) {
    setCollapsedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(groupId)) next.delete(groupId)
      else next.add(groupId)
      return next
    })
  }

  function toggleAll() {
    if (collapsedGroups.size > 0 || unassignedCollapsed) {
      setCollapsedGroups(new Set())
      setUnassignedCollapsed(false)
    } else {
      setCollapsedGroups(new Set(groups.map((g) => g.id)))
      setUnassignedCollapsed(true)
    }
  }

  const allCollapsed =
    groups.length > 0 &&
    collapsedGroups.size === groups.length &&
    (grouped.unassigned.length === 0 || unassignedCollapsed)

  if (!hasGroupedStructure) {
    return (
      <div
        data-testid="tracker-grid"
        className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4"
      >
        {trackers.map((tracker) => (
          <TrackerCard
            key={tracker.id}
            tracker={tracker}
            locked={locked.has(tracker.id)}
            pending={pendingTrackerId === tracker.id}
            onCapture={(input) => onCapture(tracker, input)}
            onBackdate={() => onBackdate(tracker)}
          />
        ))}
      </div>
    )
  }

  return (
    <div data-testid="tracker-grid" className="space-y-4">
      <div className="flex items-center justify-between gap-2 px-0.5">
        <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
          Lưới ghi nhanh
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="h-auto p-1 text-xs text-primary font-semibold hover:bg-transparent"
          onClick={toggleAll}
        >
          {allCollapsed ? 'Mở rộng tất cả' : 'Thu gọn tất cả'}
        </Button>
      </div>

      {grouped.grouped.map(({ group, trackers: groupTrackers }) => {
        const isCollapsed = collapsedGroups.has(group.id)
        return (
          <div key={group.id} className="rounded-lg border border-border/80 bg-card p-3 shadow-1">
            <button
              type="button"
              className="flex w-full items-center justify-between gap-2 text-left font-semibold cursor-pointer select-none"
              onClick={() => toggleGroup(group.id)}
            >
              <div className="flex items-center gap-2 min-w-0">
                <Folder className="size-4 text-primary shrink-0" />
                <span className="text-sm font-bold truncate text-foreground">
                  {group.name}
                </span>
                <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                  {groupTrackers.length}
                </span>
              </div>
              {isCollapsed ? (
                <ChevronDown className="size-4 text-muted-foreground ml-auto shrink-0" />
              ) : (
                <ChevronUp className="size-4 text-muted-foreground ml-auto shrink-0" />
              )}
            </button>

            {!isCollapsed && groupTrackers.length > 0 ? (
              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 border-t border-border/50 pt-2.5">
                {groupTrackers.map((tracker) => (
                  <TrackerCard
                    key={tracker.id}
                    tracker={tracker}
                    locked={locked.has(tracker.id)}
                    pending={pendingTrackerId === tracker.id}
                    onCapture={(input) => onCapture(tracker, input)}
                    onBackdate={() => onBackdate(tracker)}
                  />
                ))}
              </div>
            ) : null}
          </div>
        )
      })}

      {grouped.unassigned.length > 0 ? (
        <div className="rounded-lg border border-border/80 bg-card p-3 shadow-1">
          <button
            type="button"
            className="flex w-full items-center justify-between gap-2 text-left font-semibold cursor-pointer select-none"
            onClick={() => setUnassignedCollapsed(!unassignedCollapsed)}
          >
            <div className="flex items-center gap-2 min-w-0">
              <Sparkles className="size-4 text-muted-foreground shrink-0" />
              <span className="text-sm font-bold truncate text-foreground">
                Chưa phân nhóm
              </span>
              <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                {grouped.unassigned.length}
              </span>
            </div>
            {unassignedCollapsed ? (
              <ChevronDown className="size-4 text-muted-foreground ml-auto shrink-0" />
            ) : (
              <ChevronUp className="size-4 text-muted-foreground ml-auto shrink-0" />
            )}
          </button>

          {!unassignedCollapsed ? (
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 border-t border-border/50 pt-2.5">
             {grouped.unassigned.map((tracker) => (
               <TrackerCard
                 key={tracker.id}
                 tracker={tracker}
                 locked={locked.has(tracker.id)}
                 pending={pendingTrackerId === tracker.id}
                 onCapture={(input) => onCapture(tracker, input)}
                 onBackdate={() => onBackdate(tracker)}
               />
             ))}
           </div>
         ) : null}
       </div>
      ) : null}
    </div>
  )
}
