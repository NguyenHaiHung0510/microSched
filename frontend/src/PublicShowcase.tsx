import { useEffect, useState } from 'react'
import { ArrowRight, ArrowUpRight, CalendarDays, Grid3X3, Leaf, ListTodo, MessageCircle, NotebookPen, Pause, Play, Wallet } from 'lucide-react'
import { MimiAvatar } from '@/components/brand'
import { Button } from '@/components/ui/button'
import { homepageHref, homepageAssets, type PublicLanguage } from '@/public-home'

const screens = [
  { id: 'tasks', asset: 'task', sampleAsset: 'tasks', icon: ListTodo, vi: 'Task', en: 'Tasks',
    descriptionVi: 'Việc cần làm và checklist theo ngày.',
    descriptionEn: 'Daily tasks and checklists.' },
  { id: 'notes', asset: 'notes', sampleAsset: 'notes', icon: NotebookPen, vi: 'Ghi chú', en: 'Notes',
    descriptionVi: 'Ghi chú và checklist đã ghim.',
    descriptionEn: 'Pinned notes and checklists.' },
  { id: 'calendar', asset: 'calendar', sampleAsset: 'calendar', icon: CalendarDays, vi: 'Lịch', en: 'Calendar',
    descriptionVi: 'Lịch tháng có cả sự kiện và việc cần làm.',
    descriptionEn: 'A monthly calendar with events and tasks.' },
  { id: 'finance', asset: 'trackerFinance', sampleAsset: 'spending', icon: Wallet, vi: 'Thu chi', en: 'Finances',
    descriptionVi: 'Thu chi theo tháng và theo nhóm.',
    descriptionEn: 'Monthly income and expenses by category.' },
  { id: 'heatmap', asset: 'trackerHeatmap', sampleAsset: null, icon: Grid3X3, vi: 'Heatmap', en: 'Heatmap',
    descriptionVi: 'Số lần ghi theo ngày.',
    descriptionEn: 'Number of entries per day.' },
  { id: 'mimi', asset: 'mimiCarousel', sampleAsset: null, icon: MessageCircle, vi: 'Mimi', en: 'Mimi',
    descriptionVi: 'Mimi tạo Task ngay trong khung chat.',
    descriptionEn: 'Mimi creates a task right in the chat.' },
  { id: 'migarden', asset: 'garden', sampleAsset: null, icon: Leaf, vi: 'miGarden', en: 'miGarden',
    descriptionVi: 'Trạng thái và lịch sử tưới ở Khu A.',
    descriptionEn: 'Watering status and history for Zone A.' },
] as const

type ShowcaseScreen = (typeof screens)[number]

const motionQuery = '(prefers-reduced-motion: reduce)'

export function PublicShowcase({ language }: { language: PublicLanguage }) {
  const [selected, setSelected] = useState(0)
  const [paused, setPaused] = useState(false)
  const [hovered, setHovered] = useState(false)
  const [keyboardFocused, setKeyboardFocused] = useState(false)
  const [pageVisible, setPageVisible] = useState(() => typeof document !== 'undefined' && !document.hidden)
  const [reducedMotion, setReducedMotion] = useState(() => typeof window !== 'undefined' && !!window.matchMedia?.(motionQuery).matches)
  const [missing, setMissing] = useState<string[]>([])
  const rotating = pageVisible && !reducedMotion && !hovered && !keyboardFocused && !paused

  useEffect(() => {
    const motion = window.matchMedia?.(motionQuery)
    const onMotionChange = (event: MediaQueryListEvent) => setReducedMotion(event.matches)
    const onVisibilityChange = () => setPageVisible(!document.hidden)
    motion?.addEventListener('change', onMotionChange)
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => {
      motion?.removeEventListener('change', onMotionChange)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [])

  useEffect(() => {
    if (!rotating) return
    const timer = window.setTimeout(() => {
      if (!document.hidden) setSelected(index => (index + 1) % screens.length)
    }, 2500)
    return () => window.clearTimeout(timer)
  }, [rotating, selected])

  const vi = language === 'vi'
  const active = screens[selected]
  const project = active.id === 'mimi' || active.id === 'migarden' ? active.id : null
  const ActiveIcon = active.icon
  const sampleImage = (item: ShowcaseScreen, size: 'desktop' | 'mobile') =>
    item.sampleAsset ? `/showcase/${language}/${item.sampleAsset}-${size}.png` : undefined
  const showcaseImageFor = (item: ShowcaseScreen) => {
    const source = homepageAssets[item.asset]
    return missing.includes(source) ? undefined : source
  }
  const markMissing = (source: string) =>
    setMissing(previous => previous.includes(source) ? previous : [...previous, source])

  const showcaseImage = showcaseImageFor(active)
  const desktopSource = showcaseImage ?? sampleImage(active, 'desktop')
  const mobileSource = showcaseImage ? undefined : sampleImage(active, 'mobile')

  return (
    <section
      id="public-showcase"
      tabIndex={-1}
      aria-label={vi ? 'Ảnh giới thiệu microSched' : 'microSched screenshot gallery'}
      className="public-gallery"
      data-testid="public-gallery"
      onPointerEnter={event => { if (event.pointerType === 'mouse') setHovered(true) }}
      onPointerLeave={event => { if (event.pointerType === 'mouse') setHovered(false) }}
      onPointerDownCapture={() => setKeyboardFocused(false)}
      onKeyDownCapture={() => setKeyboardFocused(true)}
      onFocusCapture={event => setKeyboardFocused(event.target.matches(':focus-visible'))}
      onBlurCapture={event => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setKeyboardFocused(false)
      }}
    >
      <div className="public-gallery-toolbar">
        <div className="public-gallery-indicators" aria-hidden="true">
          {screens.map((screen, index) => <span key={screen.id} className="public-gallery-dot" data-active={index === selected} />)}
        </div>
        <Button type="button" variant="outline" size="lg" onClick={() => setPaused(value => !value)} aria-controls="public-showcase-image">
          {paused ? <><Play aria-hidden="true" />{vi ? 'Tiếp tục' : 'Resume'}</>
            : <><Pause aria-hidden="true" />{vi ? 'Tạm dừng' : 'Pause'}</>}
        </Button>
      </div>

      <div className="public-gallery-choices" role="group" aria-label={vi ? 'Chọn màn hình để xem' : 'Choose a showcase slide'}>
        {screens.map((item, index) => {
          const Icon = item.icon
          const showcaseThumbnail = showcaseImageFor(item)
          const thumbnailSource = showcaseThumbnail ?? sampleImage(item, 'desktop')
          return (
            <Button
              key={item.id}
              type="button"
              variant="ghost"
              className="public-gallery-choice"
              aria-pressed={index === selected}
              aria-controls="public-showcase-image"
              onClick={() => setSelected(index)}
              data-testid={`showcase-select-${item.id}`}
            >
              <span className="public-choice-media" aria-hidden="true">
                {thumbnailSource && <img
                  src={thumbnailSource}
                  alt=""
                  width="1280"
                  height="800"
                  loading="lazy"
                  onError={showcaseThumbnail ? () => markMissing(showcaseThumbnail) : undefined}
                />}
                {item.id === 'mimi' || item.id === 'migarden' ? (
                  <span className="public-choice-badge">
                    {item.id === 'mimi' ? <MimiAvatar size={showcaseThumbnail ? 'md' : 'lg'} /> : <Leaf className="public-choice-icon" />}
                  </span>
                ) : !thumbnailSource && <Icon className="public-choice-icon" />}
              </span>
              <span className="public-choice-label"><Icon aria-hidden="true" />{item[language]}</span>
            </Button>
          )
        })}
      </div>

      <figure className="public-showcase" id="public-showcase-image">
        <div className="public-showcase-stage" data-mobile-sample={mobileSource ? true : undefined}>
          {desktopSource ? <picture key={desktopSource}>
            {mobileSource && <source media="(max-width: 600px)" srcSet={mobileSource} width="390" height="844" />}
            <img
              src={desktopSource}
              width="1280"
              height="800"
              alt={project === 'mimi' ? (vi
                ? 'Kết quả tạo Task trong chat Mimi, kèm tên model và thanh ngữ cảnh.'
                : 'A task creation result in Mimi chat, with the model name and context meter.')
                : project === 'migarden' ? (vi ? 'Trạng thái và biểu đồ Khu A.' : 'Zone A status and charts.')
                  : vi ? `Màn hình ${active.vi} của microSched.` : `The microSched ${active.en} screen.`}
              onError={showcaseImage ? () => markMissing(showcaseImage) : undefined}
              fetchPriority={selected === 0 ? 'high' : 'auto'}
              data-testid="showcase-image"
            />
          </picture> : <div className="public-showcase-placeholder">
            {project === 'mimi' ? <span aria-hidden="true"><MimiAvatar size="xl" /></span> : <ActiveIcon size={48} aria-hidden="true" />}
            <strong>{active[language]}</strong>
          </div>}
        </div>

        <figcaption>
          <p aria-live={rotating ? 'off' : 'polite'} aria-atomic="true" className="public-gallery-description">
            {active.id === 'finance' && !showcaseImage
              ? (vi ? 'Theo dõi chi tiêu.' : 'Tracking expenses.')
              : (vi ? active.descriptionVi : active.descriptionEn)}
          </p>
          {showcaseImage && <p className="public-gallery-source">
            {vi
              ? 'Ảnh chụp từ bản microSched mình dùng trên production từ 21/8. Một số thông tin cá nhân được che xám.'
              : 'Screenshot from the microSched app I’ve used in production since August 21. Some personal details are grayed out.'}
          </p>}
          <div className="public-gallery-caption">
            {project && <a href={homepageHref(language, project)} className="public-text-link">
              {vi ? `Xem thêm về ${active[language]}` : `More about ${active[language]}`}<ArrowRight aria-hidden="true" size={16} />
            </a>}
            {desktopSource && !showcaseImage && <span>{vi ? 'Ảnh chụp từ ứng dụng · Dữ liệu mẫu' : 'App screenshot · Sample data'}</span>}
            {desktopSource && <a href={desktopSource} target="_blank" rel="noopener noreferrer" className="public-text-link">
              {vi ? 'Xem ảnh lớn' : 'View full image'}<ArrowUpRight aria-hidden="true" size={16} />
            </a>}
          </div>
        </figcaption>
      </figure>
    </section>
  )
}
