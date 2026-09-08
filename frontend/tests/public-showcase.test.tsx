import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { PublicShowcase } from '../src/PublicShowcase'

describe('public app showcase', () => {
  it.each(['vi', 'en'] as const)('offers all five real app screens in %s', language => {
    const html = renderToStaticMarkup(<PublicShowcase language={language} />)
    for (const screen of ['tasks', 'notes', 'calendar', 'trackers', 'spending']) {
      expect(html).toContain(`data-testid="showcase-select-${screen}"`)
      expect(html).toContain(`/showcase/${language}/${screen}-desktop.png`)
    }
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(1)
    expect(html.match(/aria-pressed="false"/g)).toHaveLength(4)
    expect(html).toContain('aria-controls="public-showcase-image"')
    expect(html).toContain('id="public-showcase-image"')
    expect(html).toContain('aria-live="polite"')
    expect(html).toContain(`/showcase/${language}/tasks-mobile.png`)
    expect(html).toContain(language === 'vi' ? 'Dữ liệu mẫu' : 'English sample data')
  })
  it('keeps the preview read-only, with local image links and no embedded app', () => {
    const html = renderToStaticMarkup(<PublicShowcase language="en" />)
    expect(html).toContain('href="/showcase/en/tasks-desktop.png"')
    expect(html).toContain('rel="noopener noreferrer"')
    // SVG's xmlns URL is a namespace, not a network request.
    expect(html).not.toMatch(/<iframe|<video|(?:href|src|srcSet)="(?:https?:|\/\/|\/api\/)/)
  })
})
