import { describe, expect, it } from 'vitest'
import { homepageLoginHref, isHomepage } from '../src/public-navigation'

describe('public homepage navigation', () => {
  it('recognizes only the explicit public path', () => {
    expect(isHomepage('/home')).toBe(true)
    expect(isHomepage('/home/?lang=en')).toBe(true)
    expect(isHomepage('/homework')).toBe(false)
    expect(isHomepage('/')).toBe(false)
  })
  it('sends homepage logins into the app, not back to the homepage', () => {
    expect(homepageLoginHref('/home?lang=en')).toBe('/auth/login?return_to=%2F')
  })
  it('preserves an internal app destination and query', () => {
    expect(homepageLoginHref('/reminder-confirm?dispatch=sample')).toBe('/auth/login?return_to=%2Freminder-confirm%3Fdispatch%3Dsample')
    expect(homepageLoginHref('/subscription?highlight=sample')).toContain('%2Fsubscription%3Fhighlight%3Dsample')
  })
  it.each(['https://example.com', '//example.com', '/\\example.com'])('does not emit an external or backslash target: %s', (target) => {
    expect(homepageLoginHref(target)).toBe('/auth/login?return_to=%2F')
  })
})
