/** Public-page navigation never replaces the server's OAuth target validation. */
export function isHomepage(location: string): boolean {
  return location.split('?')[0].replace(/\/$/, '') === '/home'
}

export function homepageLoginHref(location: string): string {
  const returnTo = isHomepage(location)
    ? '/'
    : location.startsWith('/') && !location.startsWith('//') && !location.includes('\\')
      ? location
      : '/'
  return `/auth/login?return_to=${encodeURIComponent(returnTo)}`
}

export type PublicAuthState = 'checking' | 'guest' | 'signed-in' | 'unknown'
