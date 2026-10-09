import { useRef } from 'react'
import { clampMimiRail } from '@/mimi-layout'
export function MimiRailResize({ side, width, onResize, disabled }: { side: 'left' | 'right'; width: number; onResize: (width: number) => void; disabled: boolean }) {
  const drag = useRef<{ x: number; width: number; container: number } | null>(null)
  return <div className="mimi-rail-resize" role="separator" aria-label={`Đổi độ rộng rail ${side === 'left' ? 'trái' : 'phải'}`} aria-orientation="vertical" aria-valuemin={160} aria-valuemax={320} aria-valuenow={width} aria-disabled={disabled} tabIndex={disabled ? -1 : 0} data-testid={`mimi-resize-${side}`}
    onPointerDown={(event) => { if (disabled) return; event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); drag.current = { x: event.clientX, width, container: event.currentTarget.parentElement?.clientWidth ?? 1600 } }}
    onPointerMove={(event) => { const start = drag.current; if (start) onResize(clampMimiRail(start.width + (event.clientX - start.x) * (side === 'left' ? 1 : -1), start.container)) }}
    onPointerUp={() => { drag.current = null }} onPointerCancel={() => { drag.current = null }} onLostPointerCapture={() => { drag.current = null }}
    onKeyDown={(event) => { if (disabled) return; const sign = side === 'left' ? 1 : -1; const next = event.key === 'Home' ? 160 : event.key === 'End' ? 320 : event.key === 'ArrowRight' ? width + sign * 16 : event.key === 'ArrowLeft' ? width - sign * 16 : null; if (next !== null) { event.preventDefault(); onResize(clampMimiRail(next, event.currentTarget.parentElement?.clientWidth ?? 1600)) } }} />
}
