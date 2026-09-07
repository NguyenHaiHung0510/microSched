import { LockKeyhole } from 'lucide-react'

import { Badge } from '@/components/ui/badge'

/** Presentation only: callers must already obey the existing private read gate. */
export function PrivateMarker({ testId = 'private-marker' }: { testId?: string }) {
  return (
    <Badge data-testid={testId} variant="outline" className="border-primary bg-brand-50 font-bold text-primary">
      <LockKeyhole data-icon="inline-start" aria-hidden="true" />
      Riêng tư
    </Badge>
  )
}
