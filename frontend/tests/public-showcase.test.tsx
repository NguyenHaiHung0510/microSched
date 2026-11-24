import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { PublicShowcase } from '../src/PublicShowcase'

describe('public app showcase', () => {
  it.each(['vi', 'en'] as const)('offers seven ordered slides with Task selected in %s', language => {
    const html = renderToStaticMarkup(<PublicShowcase language={language} />)
    expect(Array.from(html.matchAll(/data-testid="showcase-select-([^"]+)"/g), match => match[1]))
      .toEqual(['tasks', 'notes', 'calendar', 'finance', 'heatmap', 'mimi', 'migarden'])
    expect(html).toContain('src="/showcase/homepage/task.png"')
    expect(html).toMatch(/aria-pressed="true"[^>]*data-testid="showcase-select-tasks"/)
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(1)
    expect(html.match(/aria-pressed="false"/g)).toHaveLength(6)
    expect(html).toContain('aria-controls="public-showcase-image"')
    expect(html).toContain('id="public-showcase-image"')
    expect(html).toContain('aria-live="polite"')
    expect(html).toContain(language === 'vi' ? 'Tạm dừng' : 'Pause')
  })
  it('keeps the default showcase read-only with same-origin media', () => {
    const html = renderToStaticMarkup(<PublicShowcase language="en" />)
    expect(html).toContain('href="/showcase/homepage/task.png"')
    expect(html).toContain('rel="noopener noreferrer"')
    // SVG's xmlns URL is a namespace, not a network request.
    expect(html).not.toMatch(/<iframe|<video|(?:href|src|srcSet)="(?:https?:|\/\/|\/api\/)/)
  })

  it('uses shipped assets for the stage and thumbnails', () => {
    const html = renderToStaticMarkup(<PublicShowcase language="en" />)
    expect(html.match(/src="\/showcase\/homepage\/task\.png"/g)).toHaveLength(2)
    for (const asset of ['notes', 'calendar', 'tracker-finance', 'tracker-heatmap', 'mimi-carousel', 'garden']) {
      expect(html).toContain('src="/showcase/homepage/' + asset + '.png"')
    }
    expect(html.match(/class="public-choice-badge"/g)).toHaveLength(2)
    expect(html).toContain('since August 21. Some personal details are grayed out.')
    expect(html).not.toContain('Sample data')
  })
})
