import { useEffect, useState } from 'react'
export function useWideMimi() {
  const [wide, setWide] = useState(() => window.matchMedia('(min-width: 1024px)').matches)
  useEffect(() => { const media = window.matchMedia('(min-width: 1024px)'); const update = () => setWide(media.matches); media.addEventListener('change', update); return () => media.removeEventListener('change', update) }, [])
  return wide
}
export const MIMI_RAIL_MIN = 160
export const MIMI_RAIL_MAX = 640
const CENTER_RESERVE = 240
const SEPARATORS_AND_GAPS = 40
export function mimiRailMaximum(containerWidth: number, otherWidth: number) {
  return Math.max(MIMI_RAIL_MIN, Math.min(MIMI_RAIL_MAX, containerWidth - otherWidth - CENTER_RESERVE - SEPARATORS_AND_GAPS))
}
export function clampMimiRail(value: number, containerWidth: number, otherWidth = 220) {
  return Math.round(Math.max(MIMI_RAIL_MIN, Math.min(mimiRailMaximum(containerWidth, otherWidth), value)))
}
export function fitMimiRails(left: number, right: number, containerWidth: number, leftOpen: boolean, rightOpen: boolean) {
  const leftMin = leftOpen ? MIMI_RAIL_MIN : 44
  const rightMin = rightOpen ? MIMI_RAIL_MIN : 44
  const l = leftOpen ? Math.max(leftMin, Math.min(MIMI_RAIL_MAX, left)) : leftMin
  const r = rightOpen ? Math.max(rightMin, Math.min(MIMI_RAIL_MAX, right)) : rightMin
  const room = Math.max(leftMin + rightMin, containerWidth - CENTER_RESERVE - SEPARATORS_AND_GAPS)
  if (l + r <= room) return { left: l, right: r }
  const extra = room - leftMin - rightMin
  const desired = l + r - leftMin - rightMin
  const allocatedLeft = Math.round(extra * (l - leftMin) / Math.max(1, desired))
  return { left: leftMin + allocatedLeft, right: rightMin + extra - allocatedLeft }
}

export function rememberedMimiWidth(side: 'left' | 'right', fallback: number) {
  try { const value = Number(localStorage.getItem(`mimi-rail-width:${side}`)); return value >= 160 && value <= MIMI_RAIL_MAX ? value : fallback } catch { return fallback }
}
export function rememberMimiWidth(side: 'left' | 'right', width: number) { try { localStorage.setItem(`mimi-rail-width:${side}`, String(width)) } catch { /* Presentation preference is optional; never blocks the controller. */ } }
