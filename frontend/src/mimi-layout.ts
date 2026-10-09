import { useEffect, useState } from 'react'
export function useWideMimi() {
  const [wide, setWide] = useState(() => window.matchMedia('(min-width: 1024px)').matches)
  useEffect(() => { const media = window.matchMedia('(min-width: 1024px)'); const update = () => setWide(media.matches); media.addEventListener('change', update); return () => media.removeEventListener('change', update) }, [])
  return wide
}
export function clampMimiRail(value: number, containerWidth: number) { return Math.round(Math.max(160, Math.min(Math.min(320, Math.max(160, containerWidth * .2)), value))) }

export function rememberedMimiWidth(side: 'left' | 'right', fallback: number) {
  try { const value = Number(localStorage.getItem(`mimi-rail-width:${side}`)); return value >= 160 && value <= 320 ? value : fallback } catch { return fallback }
}
export function rememberMimiWidth(side: 'left' | 'right', width: number) { try { localStorage.setItem(`mimi-rail-width:${side}`, String(width)) } catch { /* Presentation preference is optional; never blocks the controller. */ } }
