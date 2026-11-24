import { useEffect, useState } from 'react'
import { Activity, ArrowDown, ArrowRight, ArrowUpRight, BookOpen, CalendarDays, CheckCheck, Code2, GitBranch, Leaf, ListTodo, NotebookPen } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { queryParams } from '@/lib/route'
import { creatorIntro, homepageHref, homepageView, homepageViews, type HomepageView, type PublicLanguage } from '@/public-home'
import { homepageLoginHref, isHomepage, type PublicAuthState } from '@/public-navigation'
import { PublicAbout, PublicGarden, PublicMimi } from '@/PublicProjectViews'
import { PublicShowcase } from '@/PublicShowcase'
import './public-pages.css'

export const REPOSITORY_URL = 'https://github.com/NguyenHaiHung0510/microSched'
export const CREATOR_URL = 'https://github.com/NguyenHaiHung0510'
const MIMI_DOCS_URL = `${REPOSITORY_URL}/blob/develop/docs/mimi/README.md`
type Language = PublicLanguage

const copy = {
  vi: {
    eyebrow: 'DỰ ÁN CÁ NHÂN · VỪA LÀM, VỪA HỌC',
    heading: <>Ứng dụng mình dùng <em>hằng ngày.</em></>,
    intro: 'Mình làm microSched để gom việc cần làm, ghi chú, lịch và những điều muốn theo dõi vào một chỗ. Dùng mỗi ngày, mình lại thấy chỗ cần sửa hoặc một ý tưởng muốn thử. Dự án vì thế vừa giúp mình sắp xếp cuộc sống, vừa là nơi mình học cách xây phần mềm và làm việc cùng AI agents.',
    explore: 'Khám phá microSched', source: 'Xem mã nguồn', signIn: 'Đăng nhập', open: 'Vào ứng dụng', checking: 'Đang kiểm tra…', retry: 'Thử lại', unknown: 'Chưa kiểm tra được phiên đăng nhập.',
    access: 'Đây là bản microSched mình dùng riêng; đăng nhập chỉ dành cho tài khoản được cấp quyền.',
    everyday: 'Mình dùng microSched để làm gì?',
    features: [
      ['Sắp xếp việc cần làm', 'Chia việc thành checklist, đặt hạn và điều chỉnh lịch khi kế hoạch thay đổi.'],
      ['Lưu ghi chú và ý tưởng', 'Ghi lại những điều cần nhớ, ghim ghi chú hay dùng và xem lại khi cần.'],
      ['Xem lịch trong ngày', 'Xem các sự kiện sắp tới cùng với việc cần làm để dễ sắp xếp thời gian.'],
      ['Theo dõi thói quen, chi tiêu', 'Ghi lại thói quen, chi tiêu và theo dõi các gói đăng ký sắp gia hạn.'],
    ],
    journeyLabel: 'HÀNH TRÌNH', journeyTitle: 'Từ công cụ dòng lệnh đến microSched.',
    journeyIntro: 'Ban đầu, mình chỉ muốn có một công cụ hợp với cách mình học và sắp xếp công việc. Mình bắt đầu từ dòng lệnh, thử làm ứng dụng desktop, rồi đưa nó lên web. Mỗi lần làm lại là một lần hiểu thêm về phần mềm mình đang xây.',
    chapters: [
      ['01', 'C++ · Dòng lệnh', 'Những bước đầu', 'Mình làm một chương trình nhỏ, sửa dần qua các phiên bản và bắt đầu học Git.'],
      ['02', 'Python · Flet', 'Thử làm phần mềm cùng AI', 'Mình thử làm ứng dụng desktop bằng Python và Flet, trao đổi với AI qua nhiều vòng để chỉnh sửa và đưa vào dùng mỗi ngày.'],
      ['03', 'microSched · Web', 'Làm bài bản hơn', 'Khi đưa microSched lên web, mình bắt đầu học sâu hơn về thiết kế hệ thống, triển khai và vận hành. Những vướng mắc khi dùng app cũng trở thành việc cần làm tiếp theo.'],
    ],
    methodLabel: 'CÁCH MÌNH LÀM DỰ ÁN', methodTitle: 'Học cách làm việc cùng AI agents.',
    methodBody: 'Mình dùng dự án để tìm hiểu harness engineering: tổ chức công việc với AI agents sao cho có mục tiêu rõ ràng và kiểm tra được kết quả. Mình xác định mục tiêu và phạm vi; agent điều phối có thể trực tiếp làm hoặc chia những phần việc cụ thể cho agent khác. Review độc lập, kiểm thử và ghi lại quyết định giúp mình xem thay đổi có đáp ứng yêu cầu hay không. Mình muốn xây dựng một cách làm vẫn hữu ích khi model và công cụ thay đổi.',
    methodSteps: ['Làm rõ mục tiêu', 'Làm việc đúng phạm vi', 'Review và kiểm thử', 'Ghi lại điều đã học'],
    stack: 'React · FastAPI · PostgreSQL',
    futureLabel: 'MIMI VÀ MIGARDEN', futureTitle: 'Từ màn hình ra đời sống.', futureStatus: 'Đã có trong microSched',
    futureIntro: 'Mình mở rộng microSched từ hai việc mình hay làm: sắp xếp công việc và chăm cây ngoài ban công.',
    futures: {
      mimi: ['Trợ lý trong microSched', 'Mimi giúp mình xử lý Task ngay trong app. Mình đã dùng Mimi để đổi tiêu đề cho 68 Task qua ba lượt và tạo Task ngay trong chat.'],
      migarden: ['Theo dõi và tưới cây ngoài ban công', 'Phần IoT ở Khu A đã xong. Mình có thể xem trạng thái và điều khiển tưới từ web.'],
    },
    futureOpen: 'Xem',
    ambition: 'Nhà mình đang sửa. Khi sửa xong, mình còn cần đi ống nước quanh lan can tới các chậu cây ở Khu A.',
    footerTitle: 'Bạn muốn tìm hiểu thêm?',
    footerText: 'Mình chia sẻ mã nguồn và tài liệu kỹ thuật trên GitHub. Bạn có thể tìm hiểu cách mình xây ứng dụng hoặc làm theo hướng dẫn để tự chạy một bản.',
    creator: 'Một chút về mình',
    qa: 'Bản xem thử local · Dữ liệu mẫu', qaOpen: 'Vào app với dữ liệu mẫu',
  },
  en: {
    eyebrow: 'A PERSONAL PROJECT, STILL GROWING',
    heading: <>Everyday life, in a <em>personal app.</em></>,
    intro: 'Tasks, notes, calendars and things worth keeping track of. I use microSched day to day and keep building it around real needs — both to make a tool that fits my life and to learn how to build software and work with AI agents.',
    explore: 'Explore microSched', source: 'View source', signIn: 'Sign in', open: 'Open app', checking: 'Checking session…', retry: 'Try again', unknown: 'Unable to check your app session.',
    access: 'This is my personal deployment; sign-in is limited to authorized accounts.',
    everyday: 'A day with microSched',
    features: [
      ['Work, one step at a time', 'Break tasks into checklists, set deadlines and rearrange them when plans change.'],
      ['Keep it for later', 'Save notes, ideas and the lists you return to throughout the day.'],
      ['See the calendar, plan the work', 'Bring calendars into the app, check upcoming events and reschedule tasks.'],
      ['Keep track of what matters', 'Log habits and spending, and keep an eye on subscriptions and renewals.'],
    ],
    journeyLabel: 'THE JOURNEY', journeyTitle: 'It started with a small tool.',
    journeyIntro: 'I started with a simple wish: a tool that fits studying and everyday life a little better. Each version brought something new to learn.',
    chapters: [
      ['01', 'C++ · Command line', 'The first steps', 'I built a small C++ program, improved it over time and started learning Git.'],
      ['02', 'Python · Flet', 'Experimenting with AI', 'I built a Python/Flet desktop app through repeated rounds of building, reviewing and refining with AI.'],
      ['03', 'microSched · Web', 'Building more deliberately', 'With microSched, I’m learning to design, deploy and improve a web app I use day to day.'],
    ],
    methodLabel: 'HOW I BUILD THE PROJECT', methodTitle: 'Learning to build with AI agents.',
    methodBody: 'Alongside learning to build software, I’m exploring harness engineering by organizing work with AI coding agents and checking the results. I set the goals and scope; a coordinating agent can implement changes or delegate focused tasks. Independent reviews, tests and a record of decisions help me check results and learn from them. I want that way of working to stay useful as models and tools change.',
    methodSteps: ['Clarify the goal', 'Work within scope', 'Review and test', 'Record what I learned'],
    stack: 'React · FastAPI · PostgreSQL',
    futureLabel: 'MIMI AND MIGARDEN', futureTitle: 'Beyond the screen, closer to everyday life.', futureStatus: 'In use in microSched',
    futureIntro: 'I extended microSched around two things I do regularly: organizing my work and looking after the plants on my balcony.',
    futures: {
      mimi: ['An assistant inside the app', 'Mimi helps me work with tasks inside microSched. I’ve used it to rename 68 tasks in three rounds and to create tasks right in chat.'],
      migarden: ['Monitoring and watering my balcony plants', 'The IoT work for Zone A is done. I can monitor it and control watering from the web.'],
    },
    futureOpen: 'Explore',
    ambition: 'My house is being renovated. Once that’s done, I still need to run the water line along the balcony railing to the plants in Zone A.',
    footerTitle: 'Open source. An ongoing story.',
    footerText: 'I share the source code and technical documentation on GitHub so you can explore how I built the app or follow the setup instructions to run your own instance.',
    creator: 'About me',
    qa: 'Local preview · Sample data', qaOpen: 'Open app with sample data',
  },
}

const journeySources: Record<string, { href: string; vi: string; en: string } | undefined> = {
  '01': {
    href: `${CREATOR_URL}/Code_HoTro_HocTap`,
    vi: 'Mã nguồn bản dòng lệnh trên GitHub',
    en: 'Command-line source on GitHub',
  },
  '02': {
    href: `${CREATOR_URL}/VC_QuanLyThoiGian`,
    vi: 'Mã nguồn bản desktop trên GitHub',
    en: 'Desktop app source on GitHub',
  },
}

const featureIcons = [ListTodo, NotebookPen, CalendarDays, Activity]
const views = Object.keys(homepageViews) as HomepageView[]
const futureProjects = ['mimi', 'migarden'] as const
const methodIcons = [BookOpen, GitBranch, CheckCheck, Leaf]

function usePublicLanguage() {
  const [language, updateLanguage] = useState<Language>(() => new URLSearchParams(window.location.search).get('lang') === 'vi' ? 'vi' : 'en')
  function setLanguage(next: Language) {
    const url = new URL(window.location.href)
    if (next === 'vi') url.searchParams.set('lang', 'vi')
    else url.searchParams.delete('lang')
    window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`)
    updateLanguage(next)
  }
  useEffect(() => {
    document.documentElement.lang = language
    return () => { document.documentElement.lang = 'vi' }
  }, [language])
  return { language, setLanguage }
}

export function DeniedPage() {
  const { language, setLanguage } = usePublicLanguage()
  const vi = language === 'vi'
  useEffect(() => { document.title = vi ? 'Chưa thể đăng nhập — microSched' : 'Unable to sign in — microSched' }, [vi])
  return <div className="public-page public-denied" lang={language}>
    <header className="public-header public-container">
      <a href={`/home${vi ? '?lang=vi' : ''}`} className="public-brand"><img src="/microsched.svg" width="28" height="28" alt="" />microSched</a>
      <Button variant="ghost" size="lg" onClick={() => setLanguage(vi ? 'en' : 'vi')}>{vi ? 'English' : 'Tiếng Việt'}</Button>
    </header>
    <main className="public-denied-main">
      <p className="public-eyebrow">microSched · {vi ? 'Bản dùng riêng' : 'Personal deployment'}</p>
      <h1>{vi ? 'Chưa thể đăng nhập vào microSched' : 'Unable to sign in to microSched'}</h1>
      <p>{vi ? 'Lần đăng nhập này chưa hoàn tất. Đây là bản microSched mình dùng riêng, chỉ các tài khoản được cấp quyền mới có thể vào. Nếu bạn đã có quyền truy cập, hãy quay về trang chủ và thử lại.' : 'This sign-in attempt could not be completed. This is my personal instance of microSched, with access limited to authorized accounts. If you have access, return to the homepage to try again.'}</p>
      <p>{vi ? 'Bạn cũng có thể tìm hiểu mã nguồn và tự triển khai một bản cho mình.' : 'You can also explore the source code and host your own instance.'}</p>
      <div className="public-actions">
        <Button asChild size="lg"><a href={REPOSITORY_URL} target="_blank" rel="noopener noreferrer">{vi ? 'Xem mã nguồn' : 'View source'}<ArrowRight aria-hidden="true" /></a></Button>
        <Button asChild variant="outline" size="lg"><a href={`/home${vi ? '?lang=vi' : ''}`}>{vi ? 'Về trang chủ' : 'Home'}</a></Button>
      </div>
      <a className="public-text-link" href={CREATOR_URL} target="_blank" rel="noopener noreferrer">{vi ? 'Một chút về mình' : 'About me'} <ArrowRight aria-hidden="true" size={16} /></a>
    </main>
  </div>
}

function PublicMicroSched({ language, auth }: { language: PublicLanguage; auth: PublicAuthState }) {
  const c = copy[language]
  return <>
    <section className="public-hero public-container" aria-labelledby="public-title">
      <p className="public-eyebrow">{c.eyebrow}</p>
      <div className="public-hero-copy">
        <h1 id="public-title">{c.heading}</h1>
        <div className="public-hero-intro">
          <p>{c.intro}</p>
          <div className="public-actions">
            <Button asChild size="lg"><a href="#everyday">{c.explore}<ArrowDown aria-hidden="true" /></a></Button>
            <Button asChild variant="ghost" size="lg"><a href={REPOSITORY_URL} target="_blank" rel="noopener noreferrer">{c.source}<ArrowRight aria-hidden="true" /></a></Button>
          </div>
          <p className="public-access">{c.access}</p>
          {auth === 'unknown' && <p role="status" className="public-access">{c.unknown}</p>}
        </div>
      </div>
      <PublicShowcase language={language} />
      {import.meta.env.DEV && <aside className="public-qa"><span>{c.qa}</span><Button asChild variant="outline" size="lg"><a href="/auth/dev-session" data-testid="qa-dev-login-link">{c.qaOpen}</a></Button></aside>}
    </section>
    <section id="everyday" className="public-section public-container" aria-labelledby="everyday-title">
      <h2 id="everyday-title">{c.everyday}</h2>
      <div className="public-features">{c.features.map(([title, body], i) => {
        const Icon = featureIcons[i]
        return <div className="public-feature" key={title}><Icon className="public-feature-icon" aria-hidden="true" /><div><h3>{title}</h3><p>{body}</p></div></div>
      })}</div>
    </section>
    <section className="public-section public-container public-editorial" aria-labelledby="journey-title">
      <div><p className="public-eyebrow">{c.journeyLabel}</p><h2 id="journey-title">{c.journeyTitle}</h2><p>{c.journeyIntro}</p></div>
      <ol className="public-journey">{c.chapters.map(([number, tech, title, body]) => {
        const source = journeySources[number]
        return <li key={number}>
          <span className="public-chapter-number" aria-hidden="true">{number}</span>
          <div>
            <p className="public-tech">{tech}</p>
            <h3>{title}</h3>
            <p>{body}</p>
            {source && <a href={source.href} target="_blank" rel="noopener noreferrer" className="public-text-link">
              {source[language]}<ArrowUpRight aria-hidden="true" size={16} />
            </a>}
          </div>
        </li>
      })}</ol>
    </section>
    <section className="public-section public-container public-method" aria-labelledby="method-title">
      <div className="public-editorial"><div><p className="public-eyebrow">{c.methodLabel}</p><h2 id="method-title">{c.methodTitle}</h2></div><div><p>{c.methodBody}</p><p className="public-stack"><Code2 size={18} aria-hidden="true" />{c.stack}</p></div></div>
      <ol className="public-method-steps">{c.methodSteps.map((step, i) => { const Icon = methodIcons[i]; return <li key={step}><Icon aria-hidden="true" /><span>{step}</span></li> })}</ol>
    </section>
    <section className="public-future" aria-labelledby="future-title">
      <div className="public-container">
        <div className="public-editorial"><div><p className="public-eyebrow">{c.futureLabel}</p><h2 id="future-title">{c.futureTitle}</h2></div><div><p>{c.futureIntro}</p><p className="public-status"><span aria-hidden="true" />{c.futureStatus}</p></div></div>
        <div className="public-future-projects">{futureProjects.map(item => {
          const name = homepageViews[item][language]
          const [title, body] = c.futures[item]
          return <article key={item}>
            <h3>{name}</h3>
            <div>
              <h4>{title}</h4>
              <p>{body}</p>
              <a href={homepageHref(language, item)} className="public-text-link">{c.futureOpen} {name}<ArrowRight aria-hidden="true" size={16} /></a>
            </div>
          </article>
        })}</div>
        <p className="public-ambition">{c.ambition}</p>
      </div>
    </section>
  </>
}

export default function HomePage({ auth, location, onRetry }: { auth: PublicAuthState; location: string; onRetry: () => void }) {
  const params = queryParams(location)
  const language = params.get('lang') === 'vi' ? 'vi' : 'en'
  const vi = language === 'vi'
  const view = isHomepage(location) ? homepageView(params.get('view')) : 'microsched'
  const c = copy[language]
  params.set('lang', vi ? 'en' : 'vi')

  useEffect(() => {
    document.documentElement.lang = language
    document.title = view === 'microsched'
      ? vi ? 'microSched — Một ứng dụng riêng' : 'microSched — A personal app'
      : `${homepageViews[view][language]} — microSched`
    return () => {
      document.documentElement.lang = 'vi'
      document.title = 'microSched'
    }
  }, [language, vi, view])

  return <div className="public-page" lang={language}>
    <a className="public-skip" href="#public-main">{vi ? 'Đến nội dung' : 'Skip to content'}</a>
    <header className="public-header public-home-header public-container">
      <a href={homepageHref(language)} className="public-brand" aria-label={vi ? 'Trang chủ microSched' : 'microSched homepage'}>
        <img src="/microsched.svg" width="28" height="28" alt="" />microSched
      </a>
      <nav className="public-view-nav" aria-label={vi ? 'Các mục trên trang chủ' : 'Homepage navigation'}>
        {views.map(item => <a
          key={item}
          className="public-view-link"
          href={homepageHref(language, item)}
          aria-current={view === item ? 'page' : undefined}
        >{homepageViews[item][language]}</a>)}
      </nav>
      <div className="public-header-actions">
        <Button asChild variant="ghost" size="lg"><a href={`?${params}`} hrefLang={vi ? 'en' : 'vi'} lang={vi ? 'en' : 'vi'}>{vi ? 'English' : 'Tiếng Việt'}</a></Button>
        {auth === 'signed-in' ? <Button asChild size="lg"><a href="/" data-testid="public-open-app">{c.open}<ArrowRight aria-hidden="true" /></a></Button>
          : auth === 'guest' ? <Button asChild size="lg"><a href={homepageLoginHref(location)} data-testid="login-link">{c.signIn}<ArrowRight aria-hidden="true" /></a></Button>
            : auth === 'checking' ? <Button disabled size="lg">{c.checking}</Button>
              : <Button variant="outline" size="lg" onClick={onRetry}>{c.retry}</Button>}
      </div>
    </header>
    {auth === 'unknown' && view !== 'microsched' && <div className="public-container"><p role="status" className="public-access">{c.unknown}</p></div>}
    <main id="public-main" tabIndex={-1} data-view={view}>
      {view === 'microsched' && <PublicMicroSched language={language} auth={auth} />}
      {view === 'mimi' && <PublicMimi language={language} docsUrl={MIMI_DOCS_URL} />}
      {view === 'migarden' && <PublicGarden language={language} />}
      {view === 'about' && <PublicAbout language={language} creatorUrl={CREATOR_URL} />}
    </main>
    {view === 'microsched' ? <footer className="public-footer public-container">
      <div><a className="public-repo-preview" href={REPOSITORY_URL} target="_blank" rel="noopener noreferrer" aria-label={c.source}><img src="/showcase/source-preview.png" width="838" height="600" loading="lazy" alt={language === 'vi' ? 'Một phần README của microSched trên GitHub' : 'A preview of the microSched README on GitHub'} /></a><h2>{c.footerTitle}</h2><p>{c.footerText}</p><Button asChild size="lg"><a href={REPOSITORY_URL} target="_blank" rel="noopener noreferrer">{c.source}<ArrowRight aria-hidden="true" /></a></Button></div>
      <div className="public-creator"><a className="public-profile-preview" href={CREATOR_URL} target="_blank" rel="noopener noreferrer" aria-label={c.creator}><img src="/showcase/creator-preview.png" width="846" height="520" loading="lazy" alt={language === 'vi' ? 'Phần mở đầu README giới thiệu của Hưng trên GitHub' : 'The opening of Hưng’s GitHub profile README'} /></a><p className="public-eyebrow">{c.creator}</p><a href={CREATOR_URL} target="_blank" rel="noopener noreferrer">Nguyễn Hải Hưng <ArrowRight aria-hidden="true" size={20} /></a><p>{creatorIntro[language]}</p></div>
    </footer> : <footer className="public-compact-footer public-container">
      <a className="public-text-link" href={REPOSITORY_URL} target="_blank" rel="noopener noreferrer">
        {vi ? 'Mã nguồn microSched' : 'microSched source'}
      </a>
      <a className="public-text-link" href={CREATOR_URL} target="_blank" rel="noopener noreferrer">
        {vi ? 'GitHub cá nhân' : 'GitHub profile'}
      </a>
    </footer>}
  </div>
}
