import { useEffect, useRef, useState } from 'react'
import { Activity, Wallet, ArrowUpRight, CalendarDays, ListTodo, NotebookPen } from 'lucide-react'
import { Button } from '@/components/ui/button'

const screens = [
  { id: 'tasks', icon: ListTodo, vi: 'Task', en: 'Tasks',
    descriptionVi: 'Từng bước xong một phần dự án. Tối nay vẫn kịp đi chơi.',
    descriptionEn: 'A project moving forward, one checked box at a time. And an evening left to enjoy.' },
  { id: 'notes', icon: NotebookPen, vi: 'Ghi chú', en: 'Notes',
    descriptionVi: 'Dàn ý demo, một bài học vừa hiểu ra, vài điều để lần sau đỡ quên.',
    descriptionEn: 'Demo plans, lessons learned and the little things worth remembering.' },
  { id: 'calendar', icon: CalendarDays, vi: 'Lịch', en: 'Calendar',
    descriptionVi: 'Lưới lịch tháng: giờ học, giờ làm dự án và giờ đóng laptop đi chơi.',
    descriptionEn: 'A clean monthly grid: time for class, time to build, time to close the laptop.' },
  { id: 'trackers', icon: Activity, vi: 'Báo cáo', en: 'Reports',
    descriptionVi: 'AI, server, API và một buổi hẹn. Nhìn lại thu chi, tháng này vẫn còn dư.',
    descriptionEn: 'AI tools, hosting, API experiments and a night out. This month still ends in the green.' },
  { id: 'spending', icon: Wallet, vi: 'Chi tiêu', en: 'Spending',
    descriptionVi: 'Biết tiền đi đâu, từ công cụ làm dự án đến những buổi đi chơi.',
    descriptionEn: 'See where the money goes, from building tools to evenings out.' },
] as const

export function PublicShowcase({ language }: { language: 'vi' | 'en' }) {
  const [selected, setSelected] = useState(0)
  const gallery = useRef<HTMLDivElement>(null)
  const [reducedMotion, setReducedMotion] = useState(
    () => typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
  const [visible, setVisible] = useState(false)
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  const [pageVisible, setPageVisible] = useState(() => typeof document === 'undefined' || !document.hidden)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const updateMotion = () => setReducedMotion(motion.matches)
    motion.addEventListener('change', updateMotion)

    let observer: IntersectionObserver | null = null
    if (typeof IntersectionObserver !== 'undefined' && gallery.current) {
      observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.3 })
      observer.observe(gallery.current)
    } else {
      setVisible(true)
    }

    const onVisibilityChange = () => setPageVisible(!document.hidden)
    document.addEventListener('visibilitychange', onVisibilityChange)

    return () => {
      motion.removeEventListener('change', updateMotion)
      if (observer) observer.disconnect()
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [])

  useEffect(() => {
    // Luôn tự động chuyển màn hình liên tục theo vòng lặp mượt mà.
    // Tự động dừng khi hover chuột, focus phím, tab ẩn, ra ngoài màn hình hoặc prefers-reduced-motion.
    if (reducedMotion || !visible || hovered || focused || !pageVisible) return

    const timer = window.setTimeout(() => {
      setSelected(curr => (curr + 1) % screens.length)
    }, 2000)

    return () => window.clearTimeout(timer)
  }, [reducedMotion, visible, hovered, focused, pageVisible, selected])

  const vi = language === 'vi'
  const asset = (id: string, size: string) => `/showcase/${language}/${id}-${size}.png`
  const activeScreen = screens[selected]

  return (
    <div
      ref={gallery}
      className="public-gallery"
      data-testid="public-gallery"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocusCapture={() => setFocused(true)}
      onBlurCapture={e => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
          setFocused(false)
        }
      }}
    >
      <div className="public-gallery-choices" role="group" aria-label={vi ? 'Chọn màn hình để xem' : 'Choose an app screen'}>
        {screens.map((item, index) => {
          const Icon = item.icon
          const isSelected = index === selected
          return (
            <Button
              key={item.id}
              variant="ghost"
              className="public-gallery-choice"
              aria-pressed={isSelected}
              aria-controls="public-showcase-image"
              onClick={() => setSelected(index)}
              data-testid={`showcase-select-${item.id}`}
            >
              <img src={asset(item.id, 'desktop')} alt="" width="1280" height="800" loading="lazy" />
              <span><Icon aria-hidden="true" size={18} />{vi ? item.vi : item.en}</span>
            </Button>
          )
        })}
      </div>

      <div className="public-gallery-toolbar">
        <span>{vi ? 'Một tuần học, làm và sống' : 'A week of studying, building and living'}</span>
        <div className="public-gallery-indicators" aria-hidden="true">
          {screens.map((item, index) => (
            <span
              key={item.id}
              className={`public-gallery-dot ${index === selected ? 'active' : ''}`}
            />
          ))}
        </div>
      </div>

      <figure className="public-showcase" id="public-showcase-image">
        <div className="public-showcase-stage">
          {screens.map((item, index) => {
            const isSelected = index === selected
            const title = vi ? item.vi : item.en
            return (
              <picture
                key={item.id}
                className="public-showcase-slide"
                data-active={isSelected}
                aria-hidden={!isSelected}
              >
                <source media="(max-width: 600px)" srcSet={asset(item.id, 'mobile')} width="390" height="844" />
                <img
                  src={asset(item.id, 'desktop')}
                  width="1280"
                  height="800"
                  alt={vi ? `Màn hình ${title} của microSched với dữ liệu mẫu.` : `The microSched ${title} screen with sample data.`}
                  fetchPriority={index === 0 ? 'high' : 'auto'}
                  data-testid={isSelected ? 'showcase-image' : undefined}
                />
              </picture>
            )
          })}
        </div>

        <figcaption>
          <p aria-live="polite" aria-atomic="true" className="public-gallery-description">
            {vi ? activeScreen.descriptionVi : activeScreen.descriptionEn}
          </p>
          <div className="public-gallery-caption">
            <span>{vi ? 'Ảnh chụp từ ứng dụng · Dữ liệu mẫu' : 'English sample data. The app still speaks Vietnamese xD'}</span>
            <a href={asset(activeScreen.id, 'desktop')} target="_blank" rel="noopener noreferrer" className="public-text-link">
              {vi ? 'Xem ảnh lớn' : 'View full image'}<ArrowUpRight aria-hidden="true" size={16} />
            </a>
          </div>
        </figcaption>
      </figure>
    </div>
  )
}
