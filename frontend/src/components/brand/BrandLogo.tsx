import { memo } from 'react'

export type BrandLogoVariant = 'mark' | 'wordmark' | 'full'
export type BrandLogoSize = 'sm' | 'md' | 'lg'

export interface BrandLogoProps {
  variant?: BrandLogoVariant
  size?: BrandLogoSize
  className?: string
  showTagline?: boolean
}

const sizeStyles: Record<BrandLogoSize, { mark: string; wordmark: string; sub: string }> = {
  sm: { mark: 'size-6', wordmark: 'h-4 w-auto', sub: 'text-[9px]' },
  md: { mark: 'size-8', wordmark: 'h-6 w-auto', sub: 'text-[10px]' },
  lg: { mark: 'size-12', wordmark: 'h-8 w-auto', sub: 'text-xs' },
}

export const BrandLogo = memo(function BrandLogo({
  variant = 'full',
  size = 'md',
  className = '',
  showTagline = true,
}: BrandLogoProps) {
  const s = sizeStyles[size] || sizeStyles.md

  const MarkSvg = (
    <img
      src="/brand/microsched-mark.svg"
      alt="microSched Layered Calendar Bloom"
      className={`${s.mark} shrink-0 object-contain select-none transition-transform duration-300 motion-safe:hover:scale-105`}
    />
  )

  const WordmarkSvg = (
    <img
      src="/brand/microsched-wordmark.svg"
      alt="microSched"
      className={`${s.wordmark} shrink-0 object-contain select-none`}
    />
  )

  if (variant === 'mark') {
    return <span data-testid="brand-logo" className={`inline-flex items-center ${className}`}>{MarkSvg}</span>
  }

  if (variant === 'wordmark') {
    return <span data-testid="brand-logo" className={`inline-flex items-center ${className}`}>{WordmarkSvg}</span>
  }

  return (
    <div data-testid="brand-logo" className={`inline-flex items-center gap-2.5 select-none ${className}`}>
      {MarkSvg}
      <div className="flex flex-col justify-center leading-none">
        {WordmarkSvg}
        {showTagline && (
          <span className={`font-mono tracking-widest uppercase text-[#CFA348] mt-1 font-semibold ${s.sub}`}>
            Plan · Progress · Bloom
          </span>
        )}
      </div>
    </div>
  )
})
