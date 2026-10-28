import { memo } from 'react'

export type MimiState = 'idle' | 'thinking' | 'executing' | 'ready'
export type MimiSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl'
export interface MimiAvatarProps {
  state?: MimiState
  size?: MimiSize
  className?: string
  showGlow?: boolean
  ariaLabel?: string
}
const sizes: Record<MimiSize, string> = { xs: 'size-6', sm: 'size-6', md: 'size-8', lg: 'size-12', xl: 'size-16' }
const labels: Record<MimiState, string> = { idle: 'Mimi', thinking: 'Mimi đang suy nghĩ', executing: 'Mimi đang thực thi', ready: 'Mimi đã sẵn sàng' }
// Owner chose one immutable identity; surrounding UI carries lifecycle status.
export const MimiAvatar = memo(function MimiAvatar({ state = 'idle', size = 'md', className = '', ariaLabel }: MimiAvatarProps) {
  return <span data-testid="mimi-avatar" data-state={state} role="img" aria-label={ariaLabel ?? labels[state]} className={`inline-flex shrink-0 items-center justify-center select-none ${sizes[size]} ${className}`}><img src="/brand/principal-mimi-logo.svg" alt="" aria-hidden="true" className="size-full object-contain" /></span>
})
