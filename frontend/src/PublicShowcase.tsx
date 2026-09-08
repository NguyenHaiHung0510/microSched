import { useEffect, useRef, useState } from 'react'
import { Activity, Wallet, Pause, Play, ArrowUpRight, CalendarDays, ListTodo, NotebookPen } from 'lucide-react'
import { Button } from '@/components/ui/button'

const screens = [
  { id: 'tasks', icon: ListTodo, vi: 'Task', en: 'Tasks',
    descriptionVi: 'Từng bước xong một phần dự án. Tối nay vẫn kịp đi chơi.',
    descriptionEn: 'A project moving forward, one checked box at a time. And an evening left to enjoy.' },
  { id: 'notes', icon: NotebookPen, vi: 'Ghi chú', en: 'Notes',
    descriptionVi: 'Dàn ý demo, một bài học vừa hiểu ra, vài điều để lần sau đỡ quên.',
    descriptionEn: 'Demo plans, lessons learned and the little things worth remembering.' },
  { id: 'calendar', icon: CalendarDays, vi: 'Lịch', en: 'Calendar',
    descriptionVi: 'Có giờ học, giờ làm dự án và giờ đóng laptop đi chơi.',
    descriptionEn: 'Time for class, time to build, time to close the laptop.' },
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
  const [playing, setPlaying] = useState(() => typeof window !== 'undefined' && typeof window.matchMedia === 'function' && !window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const [visible, setVisible] = useState(false)
  const [hovered, setHovered] = useState(false)
  const [pageVisible, setPageVisible] = useState(() => typeof document === 'undefined' || !document.hidden)
  useEffect(() => {
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const stopForMotion = () => { if (motion.matches) setPlaying(false) }
    motion.addEventListener('change', stopForMotion)
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.35 })
    if (gallery.current) observer.observe(gallery.current)
    const visibility = () => setPageVisible(!document.hidden)
    document.addEventListener('visibilitychange', visibility)
    return () => { observer.disconnect(); motion.removeEventListener('change', stopForMotion); document.removeEventListener('visibilitychange', visibility) }
  }, [])
  useEffect(() => {
    if (!playing || !visible || hovered || !pageVisible) return
    // A single five-screen tour; no polling, network timer or endless rotation.
    const timer = window.setTimeout(() => {
      if (selected === screens.length - 1) setPlaying(false)
      else setSelected(selected + 1)
    }, 7000)
    return () => window.clearTimeout(timer)
  }, [playing, visible, hovered, pageVisible, selected])
  const vi = language === 'vi'
  const asset = (id: string, size: string) => `/showcase/${language}/${id}-${size}.png`
  const screen = screens[selected]
  const title = vi ? screen.vi : screen.en
  return <div ref={gallery} className="public-gallery" data-testid="public-gallery" onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)} onFocusCapture={e => { if (!(e.target as HTMLElement).closest('[data-testid="showcase-play"]')) setPlaying(false) }}>
    <div className="public-gallery-choices" role="group" aria-label={vi ? 'Chọn màn hình để xem' : 'Choose an app screen'}>
      {screens.map((item, index) => {
        const Icon = item.icon
        return <Button key={item.id} variant="ghost" className="public-gallery-choice"
          aria-pressed={index === selected} aria-controls="public-showcase-image"
          onClick={() => { setPlaying(false); setSelected(index) }} data-testid={`showcase-select-${item.id}`}>
          <img src={asset(item.id, 'desktop')} alt="" width="1280" height="800" loading="lazy" />
          <span><Icon aria-hidden="true" size={18} />{vi ? item.vi : item.en}</span>
        </Button>
      })}
    </div>
    <div className="public-gallery-toolbar"><span>{vi ? 'Một tuần học, làm và sống' : 'A week of studying, building and living'}</span>
      <Button variant="ghost" size="lg" data-testid="showcase-play" onClick={() => {
        if (!playing && selected === screens.length - 1) setSelected(0)
        setPlaying(p => !p)
      }}>
        {playing ? <Pause size={16} aria-hidden="true" /> : <Play size={16} aria-hidden="true" />}{playing ? (vi ? 'Dừng tự chuyển' : 'Pause tour') : (vi ? 'Tự xem 5 màn hình' : 'Play tour')}
      </Button></div>
    <figure className="public-showcase" id="public-showcase-image">
      <picture key={`${language}-${screen.id}`} className="public-gallery-frame">
        <source media="(max-width: 600px)" srcSet={asset(screen.id, 'mobile')} width="390" height="844" />
        <img src={asset(screen.id, 'desktop')} width="1280" height="800"
          alt={vi ? `Màn hình ${title} của microSched với dữ liệu mẫu.` : `The microSched ${title} screen with sample data.`}
          fetchPriority="high" data-testid="showcase-image" />
      </picture>
      <figcaption>
        <p aria-live={playing ? 'off' : 'polite'} aria-atomic="true" className="public-gallery-description">{vi ? screen.descriptionVi : screen.descriptionEn}</p>
        <div className="public-gallery-caption">
          <span>{vi ? 'Ảnh chụp từ ứng dụng · Dữ liệu mẫu' : 'English sample data. The app still speaks Vietnamese xD'}</span>
          <a href={asset(screen.id, 'desktop')} target="_blank" rel="noopener noreferrer" className="public-text-link">
            {vi ? 'Xem ảnh lớn' : 'View full image'}<ArrowUpRight aria-hidden="true" size={16} />
          </a>
        </div>
      </figcaption>
    </figure>
  </div>
}
