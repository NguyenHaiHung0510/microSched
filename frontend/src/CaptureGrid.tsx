import { TrackerCard } from '@/TrackerCard'
import type { Tracker } from '@/tracker-ui'

type CaptureGridProps = {
  trackers: Tracker[]
  locked: ReadonlySet<string>
  pendingTrackerId: string | null
  onCapture: (tracker: Tracker, input?: string) => void
  onBackdate: (tracker: Tracker) => void
}

export function CaptureGrid({
  trackers,
  locked,
  pendingTrackerId,
  onCapture,
  onBackdate,
}: CaptureGridProps) {
  if (trackers.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        Chưa có tracker nào. Bấm “Tracker mới” để bắt đầu.
      </p>
    )
  }
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
