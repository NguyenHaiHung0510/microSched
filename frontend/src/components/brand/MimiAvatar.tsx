import { memo } from 'react'
import '@/brand-motion.css'

export type MimiState = 'idle' | 'thinking' | 'executing' | 'ready'
export type MimiSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl'

export interface MimiAvatarProps {
  state?: MimiState
  size?: MimiSize
  className?: string
  showGlow?: boolean
  ariaLabel?: string
}

const sizeMap: Record<MimiSize, { class: string; px: number }> = {
  xs: { class: 'size-4', px: 16 },
  sm: { class: 'size-6', px: 24 },
  md: { class: 'size-8', px: 32 },
  lg: { class: 'size-12', px: 48 },
  xl: { class: 'size-16', px: 64 },
}

const stateLabels: Record<MimiState, string> = {
  idle: 'Mimi đang lắng nghe (A Quiet Bud)',
  thinking: 'Mimi đang suy nghĩ (Ideas Unfurl)',
  executing: 'Mimi đang thực thi (Turning Plans into Progress)',
  ready: 'Mimi đã sẵn sàng (All Set)',
}

const stateFiles: Record<MimiState, string> = {
  idle: '/brand/mimi-idle.svg',
  thinking: '/brand/mimi-thinking.svg',
  executing: '/brand/mimi-executing.svg',
  ready: '/brand/mimi-ready.svg',
}

const motionClasses: Record<MimiState, string> = {
  idle: 'brand-breathe',
  thinking: 'brand-pulse-glow',
  executing: 'brand-orbit-rotor',
  ready: 'brand-ready-badge',
}

export const MimiAvatar = memo(function MimiAvatar({
  state = 'idle',
  size = 'md',
  className = '',
  showGlow = false,
  ariaLabel,
}: MimiAvatarProps) {
  const resolvedSize = sizeMap[size] || sizeMap.md
  const label = ariaLabel || stateLabels[state]
  const svgSrc = stateFiles[state] || stateFiles.idle
  const motionClass = motionClasses[state] || motionClasses.idle

  return (
    <div
      data-testid="mimi-avatar"
      data-state={state}
      role="img"
      aria-label={label}
      className={`relative inline-flex items-center justify-center shrink-0 select-none ${resolvedSize.class} ${className}`}
    >
      {showGlow && (
        <span
          aria-hidden="true"
          className={`absolute inset-0 rounded-full blur-sm transition-opacity duration-300 ${
            state === 'thinking'
              ? 'bg-[#CFA348]/35 animate-pulse'
              : state === 'executing'
              ? 'bg-[#DE7A85]/30 animate-pulse'
              : state === 'ready'
              ? 'bg-[#CFA348]/40'
              : 'bg-[#F5B8BA]/20'
          }`}
        />
      )}

      <img
        src={svgSrc}
        alt={label}
        className={`size-full object-contain overflow-visible ${motionClass}`}
      />
    </div>
  )
})
