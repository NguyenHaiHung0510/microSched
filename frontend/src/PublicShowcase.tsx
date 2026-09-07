import { useState } from 'react'
import { Activity, ArrowUpRight, CalendarDays, ListTodo, NotebookPen } from 'lucide-react'
import { Button } from '@/components/ui/button'

const screens = [
  { id: 'tasks', icon: ListTodo, vi: 'Task', en: 'Tasks',
    descriptionVi: 'Chia việc thành checklist, đặt hạn và theo dõi những việc còn dang dở.',
    descriptionEn: 'Break work into checklists, set deadlines and keep unfinished tasks in view.' },
  { id: 'notes', icon: NotebookPen, vi: 'Ghi chú', en: 'Notes',
    descriptionVi: 'Lưu ý tưởng, ghim ghi chú cần dùng và đánh dấu từng mục ngay trên thẻ.',
    descriptionEn: 'Save ideas, pin useful notes and check off items right on the card.' },
  { id: 'calendar', icon: CalendarDays, vi: 'Lịch', en: 'Calendar',
    descriptionVi: 'Xem lịch và công việc theo ngày để dễ sắp xếp thời gian.',
    descriptionEn: 'See events and tasks by date to make room for what is coming up.' },
  { id: 'trackers', icon: Activity, vi: 'Theo dõi', en: 'Trackers',
    descriptionVi: 'Ghi lại thói quen, chi tiêu và xem các số liệu tổng hợp theo thời gian.',
    descriptionEn: 'Log habits and spending, then look back at summaries over time.' },
] as const

export function PublicShowcase({ language }: { language: 'vi' | 'en' }) {
  const [selected, setSelected] = useState(0)
  const vi = language === 'vi'
  const screen = screens[selected]
  const title = vi ? screen.vi : screen.en
  return <div className="public-gallery" data-testid="public-gallery">
    <div className="public-gallery-choices" role="group" aria-label={vi ? 'Chọn màn hình để xem' : 'Choose an app screen'}>
      {screens.map((item, index) => {
        const Icon = item.icon
        return <Button key={item.id} variant="ghost" className="public-gallery-choice"
          aria-pressed={index === selected} aria-controls="public-showcase-image"
          onClick={() => setSelected(index)} data-testid={`showcase-select-${item.id}`}>
          <img src={`/showcase/${item.id}-desktop.png`} alt="" width="1280" height="800" loading="lazy" />
          <span><Icon aria-hidden="true" size={18} />{vi ? item.vi : item.en}</span>
        </Button>
      })}
    </div>
    <figure className="public-showcase" id="public-showcase-image">
      <picture>
        <source media="(max-width: 600px)" srcSet={`/showcase/${screen.id}-mobile.png`} width="390" height="844" />
        <img src={`/showcase/${screen.id}-desktop.png`} width="1280" height="800"
          alt={vi ? `Màn hình ${title} của microSched với dữ liệu mẫu.` : `The microSched ${title} screen with sample data.`}
          fetchPriority="high" data-testid="showcase-image" />
      </picture>
      <figcaption>
        <p aria-live="polite" aria-atomic="true" className="public-gallery-description">{vi ? screen.descriptionVi : screen.descriptionEn}</p>
        <div className="public-gallery-caption">
          <span>{vi ? 'Ảnh chụp từ ứng dụng · Dữ liệu mẫu' : 'Real app screenshots · Sample data'}</span>
          <a href={`/showcase/${screen.id}-desktop.png`} target="_blank" rel="noopener noreferrer" className="public-text-link">
            {vi ? 'Xem ảnh lớn' : 'View full image'}<ArrowUpRight aria-hidden="true" size={16} />
          </a>
        </div>
      </figcaption>
    </figure>
  </div>
}
