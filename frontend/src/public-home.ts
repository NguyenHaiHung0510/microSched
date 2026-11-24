export type PublicLanguage = 'vi' | 'en'

export const creatorIntro = {
  vi: 'Mình là sinh viên PTIT. Mình muốn trở thành AI engineer và đang tự học để theo hướng đó.',
  en: 'I’m a PTIT student. I want to become an AI engineer, and I’m learning on my own to get there.',
}

export const homepageViews = {
  microsched: { vi: 'microSched', en: 'microSched' },
  mimi: { vi: 'Mimi', en: 'Mimi' },
  migarden: { vi: 'miGarden', en: 'miGarden' },
  about: { vi: 'Về mình', en: 'About me' },
} as const

export type HomepageView = keyof typeof homepageViews

export function homepageView(value: string | null): HomepageView {
  if (value === 'mimi' || value === 'migarden' || value === 'about') return value
  return 'microsched'
}

export function homepageHref(language: PublicLanguage, view: HomepageView = 'microsched') {
  return `/home?lang=${language}&view=${view}`
}

export const homepageAssets = {
  task: '/showcase/homepage/task.png',
  notes: '/showcase/homepage/notes.png',
  calendar: '/showcase/homepage/calendar.png',
  trackerFinance: '/showcase/homepage/tracker-finance.png',
  trackerHeatmap: '/showcase/homepage/tracker-heatmap.png',
  garden: '/showcase/homepage/garden.png',
  mimiFirst: '/showcase/homepage/mimi-first.png',
  mimiSecond: '/showcase/homepage/mimi-second.png',
  mimiCarousel: '/showcase/homepage/mimi-carousel.png',
  balconyOriginal: '/showcase/homepage/balcony-original.jpg',
  balconyKit: '/showcase/homepage/balcony-kit.jpg',
  balconySketch: '/showcase/homepage/balcony-sketch.jpg',
  cabinet: '/showcase/homepage/cabinet.jpg',
} as const
