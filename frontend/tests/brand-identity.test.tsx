import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { BrandLogo, MimiAvatar, OrbitIndicator } from '../src/components/brand'

describe('Brand Identity System (microSched · Mimi · Orbit)', () => {
  describe('MimiAvatar', () => {
    it.each(['idle', 'thinking', 'executing', 'ready'] as const)('renders Mimi in %s state without Lucide Bot', (state) => {
      const html = renderToStaticMarkup(<MimiAvatar state={state} size="md" />)
      expect(html).toContain('data-testid="mimi-avatar"')
      expect(html).toContain(`data-state="${state}"`)
      expect(html).toContain('role="img"')
      expect(html).toContain('<svg')
      // Guardrail: must not contain Lucide bot SVG or lucide classes
      expect(html).not.toContain('lucide-bot')
      expect(html).not.toContain('lucide')
      // Must use brand colors
      expect(html).toContain('#CFA348')
      expect(html).toContain('#4A1521')
    })

    it('renders accessible state descriptions', () => {
      const htmlIdle = renderToStaticMarkup(<MimiAvatar state="idle" />)
      expect(htmlIdle).toContain('aria-label="Mimi đang lắng nghe (A Quiet Bud)"')

      const htmlThinking = renderToStaticMarkup(<MimiAvatar state="thinking" />)
      expect(htmlThinking).toContain('aria-label="Mimi đang suy nghĩ (Ideas Unfurl)"')

      const htmlExecuting = renderToStaticMarkup(<MimiAvatar state="executing" />)
      expect(htmlExecuting).toContain('aria-label="Mimi đang thực thi (Turning Plans into Progress)"')

      const htmlReady = renderToStaticMarkup(<MimiAvatar state="ready" />)
      expect(htmlReady).toContain('aria-label="Mimi đã sẵn sàng (All Set)"')
    })
  })

  describe('BrandLogo', () => {
    it('renders full brand logo with Layered Calendar Bloom mark and wordmark', () => {
      const html = renderToStaticMarkup(<BrandLogo variant="full" size="md" />)
      expect(html).toContain('data-testid="brand-logo"')
      expect(html).toContain('micro')
      expect(html).toContain('Sched')
      expect(html).toContain('Plan · Progress · Bloom')
      expect(html).toContain('#CFA348')
      expect(html).toContain('#4A1521')
    })

    it('renders mark-only variant cleanly', () => {
      const html = renderToStaticMarkup(<BrandLogo variant="mark" size="sm" />)
      expect(html).toContain('data-testid="brand-logo"')
      expect(html).toContain('<svg')
      expect(html).not.toContain('Plan · Progress · Bloom')
    })
  })

  describe('OrbitIndicator', () => {
    it.each(['standby', 'pulse', 'active', 'complete'] as const)('renders Orbit in %s status', (status) => {
      const html = renderToStaticMarkup(<OrbitIndicator status={status} size="md" />)
      expect(html).toContain('data-testid="orbit-indicator"')
      expect(html).toContain(`data-status="${status}"`)
      expect(html).toContain('role="status"')
      expect(html).toContain('<svg')
      expect(html).toContain('#CFA348')
    })
  })
})
