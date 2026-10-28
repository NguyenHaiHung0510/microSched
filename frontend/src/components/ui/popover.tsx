import { Popover as Primitive } from 'radix-ui'
import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

export function Popover(props: ComponentProps<typeof Primitive.Root>) { return <Primitive.Root {...props} /> }
export function PopoverTrigger(props: ComponentProps<typeof Primitive.Trigger>) { return <Primitive.Trigger {...props} /> }
export function PopoverClose(props: ComponentProps<typeof Primitive.Close>) { return <Primitive.Close {...props} /> }
export function PopoverContent({ className, sideOffset = 8, ...props }: ComponentProps<typeof Primitive.Content>) {
  return <Primitive.Portal><Primitive.Content sideOffset={sideOffset} collisionPadding={12}
    className={cn('z-50 w-[min(640px,calc(100vw-24px))] max-h-[min(85dvh,var(--radix-popover-content-available-height))] overflow-y-auto overscroll-contain rounded-2xl border bg-popover p-4 text-popover-foreground shadow-lg outline-none', className)} {...props} /></Primitive.Portal>
}
