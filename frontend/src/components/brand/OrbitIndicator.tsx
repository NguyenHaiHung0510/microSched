import { memo } from 'react'
import '@/brand-motion.css'

export type OrbitStatus = 'standby' | 'pulse' | 'active' | 'complete'
export type OrbitSize = 'sm' | 'md' | 'lg'

export interface OrbitIndicatorProps {
  status?: OrbitStatus
  size?: OrbitSize
  className?: string
  ariaLabel?: string
}

const orbitSizes: Record<OrbitSize, string> = {
  sm: 'size-6',
  md: 'size-8',
  lg: 'size-12',
}

const statusLabels: Record<OrbitStatus, string> = {
  standby: 'Tự động hóa sẵn sàng (Standby)',
  pulse: 'Đang gửi nhịp heartbeat (Pulse)',
  active: 'Đang thực hiện tự động hóa (Petals in Flight)',
  complete: 'Đã hoàn tất tự động hóa (Complete)',
}

const statusMotions: Record<OrbitStatus, string> = {
  standby: 'brand-breathe',
  pulse: 'brand-pulse-glow',
  active: 'brand-orbit-rotor',
  complete: 'brand-ready-badge',
}

export const OrbitIndicator = memo(function OrbitIndicator({
  status = 'standby',
  size = 'md',
  className = '',
  ariaLabel,
}: OrbitIndicatorProps) {
  const sizeClass = orbitSizes[size] || orbitSizes.md
  const label = ariaLabel || statusLabels[status]
  const motionClass = statusMotions[status] || statusMotions.standby

  return (
    <div
      data-testid="orbit-indicator"
      data-status={status}
      role="status"
      aria-label={label}
      className={`relative inline-flex items-center justify-center shrink-0 ${sizeClass} ${className}`}
    >
      <img
        src="/brand/orbit-blossom.svg"
        alt={label}
        data-state={status}
        className={`size-full object-contain overflow-visible ${motionClass}`}
      />
    </div>
  )
})
