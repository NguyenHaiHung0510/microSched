import { useEffect, useRef, useState } from 'react'

function Blossom({ className }: { className: string }) {
  return <svg className={className} viewBox="0 0 180 180" focusable="false"><g className="mimi-blossom-petals">{[0,72,144,216,288].map((angle) => <path key={angle} transform={`rotate(${angle} 90 90)`} d="M90 90C44 80 43 30 72 27L90 36L108 27C137 30 136 80 90 90Z" />)}</g><g className="mimi-blossom-stamens">{[0,60,120,180,240,300].map((angle) => <path key={angle} transform={`rotate(${angle} 90 90)`} d="M90 90L90 68M88 66L92 66" />)}</g><circle cx="90" cy="90" r="6" className="mimi-blossom-heart" /></svg>
}
export function MimiBackdrop({ active = false }: { active?: boolean }) {
  const root = useRef<HTMLDivElement>(null)
  const [paused, setPaused] = useState(() => document.hidden)
  useEffect(() => {
    let visible = true
    const update = () => setPaused(document.hidden || !visible)
    document.addEventListener('visibilitychange', update)
    const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; update() })
    if (root.current) observer.observe(root.current)
    return () => { document.removeEventListener('visibilitychange', update); observer.disconnect() }
  }, [])
  return <div ref={root} aria-hidden="true" className={`mimi-backdrop ${active ? 'mimi-backdrop-active' : ''}`} data-paused={paused} data-testid="mimi-backdrop"><div className="mimi-floral-corner mimi-floral-bottom" /><div className="mimi-floral-corner mimi-floral-top" /><Blossom className="mimi-blossom mimi-blossom-one" /><Blossom className="mimi-blossom mimi-blossom-two" /><Blossom className="mimi-blossom mimi-blossom-three" />{[0,1,2,3,4,5].map((index) => <svg key={index} className={`mimi-petal mimi-petal-${index}`} viewBox="0 0 40 50" focusable="false"><path d="M7 44C-1 20 16 2 32 4C34 19 30 35 7 44Z" /><path className="mimi-petal-crease" d="M7 44L30 7" /></svg>)}</div>
}
