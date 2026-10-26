import { useEffect } from 'react'
import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { saveMimiResponseTiming, type MimiConversation } from '@/mimi-api'
import { MimiResponseClock } from '@/mimi-response-timing'

const clocks = new WeakMap<QueryClient, MimiResponseClock>()
const observers = new WeakMap<MimiResponseClock, Map<string, number>>()
function clockFor(client: QueryClient) {
  let clock = clocks.get(client)
  if (!clock) { clock = new MimiResponseClock(); clocks.set(client, clock) }
  return clock
}

/** Event driven: two frames once per canonical response, one bounded write.
 * Never await telemetry in the send/confirmation mutation or redispatch a model.
 */
export function useMimiResponseTiming(conversation: MimiConversation | null | undefined) {
  const client = useQueryClient()
  const clock = clockFor(client)
  const conversationId = conversation?.id
  useEffect(() => {
    if (!conversationId) return
    let counts = observers.get(clock)
    if (!counts) { counts = new Map(); observers.set(clock, counts) }
    counts.set(conversationId, (counts.get(conversationId) ?? 0) + 1)
    return () => {
      const remaining = (counts.get(conversationId) ?? 1) - 1
      counts.set(conversationId, remaining)
      if (!remaining) { clock.hideConversation(conversationId); counts.delete(conversationId) }
    }
  }, [clock, conversationId])
  useEffect(() => {
    const hide = () => { if (document.visibilityState !== 'visible') clock.hide() }
    document.addEventListener('visibilitychange', hide)
    return () => document.removeEventListener('visibilitychange', hide)
  }, [clock])
  useEffect(() => {
    if (!conversation) return
    const frames: number[] = []
    let cancelled = false
    const send = () => {
      for (const receipt of clock.receipts.values()) {
        if (receipt.conversationId !== conversation.id || receipt.state !== 'ready') continue
        receipt.state = 'sending'
        void saveMimiResponseTiming(receipt.conversationId, receipt.body).then(saved => {
          if (Object.entries(receipt.body).some(([key, value]) => saved[key as keyof typeof saved] !== value)) throw new Error('Timing receipt mismatch')
          receipt.state = 'saved'
          for (const [key, stored] of clock.receipts) if (stored === receipt) clock.receipts.delete(key)
          // A single read refresh after ACK, never a polling loop.
          void client.invalidateQueries({ queryKey: ['mimi'] })
        }).catch(() => { receipt.state = 'unknown' })
      }
    }
    for (const { start, response, key } of clock.candidates(conversation.id, conversation.response_timings?.responses ?? [])) {
      const elements = [...document.querySelectorAll<HTMLElement>(`[data-mimi-response-id="${response.target_id}"]`)]
      if (!elements.length) continue // No committed canonical DOM, so no observation.
      const visible = () => elements.some(element => {
        const rect = element.getBoundingClientRect()
        if (!element.isConnected || !element.getClientRects().length) return false
        let top = Math.max(rect.top, 0), left = Math.max(rect.left, 0)
        let bottom = Math.min(rect.bottom, innerHeight), right = Math.min(rect.right, innerWidth)
        for (let node: HTMLElement | null = element; node; node = node.parentElement) {
          const style = getComputedStyle(node)
          if (style.display === 'none' || style.visibility !== 'visible' || Number(style.opacity) === 0) return false
          if (node !== element) {
            const clip = node.getBoundingClientRect()
            if (/(auto|scroll|hidden|clip)/.test(style.overflowY)) { top = Math.max(top, clip.top); bottom = Math.min(bottom, clip.bottom) }
            if (/(auto|scroll|hidden|clip)/.test(style.overflowX)) { left = Math.max(left, clip.left); right = Math.min(right, clip.right) }
          }
        }
        return bottom > top && right > left
      })
      const complete = () => {
        if (cancelled) return
        clock.complete(key, start, response, performance.now(),
          start.hidden || document.visibilityState !== 'visible' ? 'hidden' : !visible() ? 'offscreen' : 'visible_paint')
        send()
      }
      // Auto-follow scroll is itself scheduled for the next frame. Testing
      // viewport intersection before that frame would mark ordinary new replies
      // offscreen, despite their canonical paint becoming visible immediately.
      if (start.hidden || document.visibilityState !== 'visible') complete()
      else frames.push(requestAnimationFrame(() => frames.push(requestAnimationFrame(complete))))
    }
    send()
    return () => { cancelled = true; frames.forEach(cancelAnimationFrame) }
  }, [client, clock, conversation])
  return {
    begin: (conversationId: string, sourceId: string, phase: 'send' | 'resume' | 'confirmation', runId: string | null = null) => {
      clock.begin({ conversationId, sourceId, phase, runId, started: performance.now(), hidden: document.visibilityState !== 'visible' })
    },
    bind: clock.bind.bind(clock),
  }
}
