import type { DayAnnotation } from '@/calendar-scroll'
import type { CommandInput } from '@/lib/outbox-adapters'

export function annotationDeleteInput(annotation: Pick<DayAnnotation, 'id' | 'is_private'>): CommandInput {
  return { path: `/api/calendar/annotations/${annotation.id}`, entityId: annotation.id,
    requiresPrivate: annotation.is_private }
}
