import { memo, useCallback } from 'react'

import { TrackerCard } from '@/TrackerCard'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import type { Tracker } from '@/tracker-ui'

const CaptureGridItem = memo(function CaptureGridItem({
  tracker,
  locked,
  pending,
  onCapture,
  onBackdate,
}: {
  tracker: Tracker
  locked: boolean
  pending: boolean
  onCapture: (tracker: Tracker, input?: string) => void
  onBackdate: (tracker: Tracker) => void
}) {
  const handleCapture = useCallback((input?: string) => onCapture(tracker, input), [tracker, onCapture])
  const handleBackdate = useCallback(() => onBackdate(tracker), [tracker, onBackdate])
  return (
    <TrackerCard
      tracker={tracker}
      locked={locked}
      pending={pending}
      onCapture={handleCapture}
      onBackdate={handleBackdate}
    />
  )
})

type CaptureGridProps = {
  trackers: Tracker[]
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
  locked,
  pendingTrackerId,
  loading,
  error,
  onRetry,
  onCapture,
  onBackdate,
}: CaptureGridProps) {
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
  return (
    <div
      data-testid="tracker-grid"
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4"
    >
      {trackers.map((tracker) => (
        <CaptureGridItem
          key={tracker.id}
          tracker={tracker}
          locked={locked.has(tracker.id)}
          pending={pendingTrackerId === tracker.id}
          onCapture={onCapture}
          onBackdate={onBackdate}
        />
      ))}
    </div>
  )
}
