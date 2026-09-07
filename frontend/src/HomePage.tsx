import { useEffect, useState } from 'react'
import { ArrowDown, ArrowRight, Code2, Leaf, ListTodo, NotebookPen, CalendarDays, Activity, GitBranch, CheckCheck, BookOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { homepageLoginHref, type PublicAuthState } from '@/public-navigation'
import './public-pages.css'

export const REPOSITORY_URL = 'https://github.com/NguyenHaiHung0510/microSched'
export const CREATOR_URL = 'https://github.com/NguyenHaiHung0510'
type Language = 'vi' | 'en'

const copy = {
  vi: {
    eyebrow: 'MỘT DỰ ÁN CÁ NHÂN, VẪN ĐANG LỚN LÊN',
    heading: <>Những việc hằng ngày, trong một <em>ứng dụng riêng.</em></>,
    intro: 'Công việc, ghi chú, lịch và những điều cần theo dõi. microSched được Hưng dùng mỗi ngày và tiếp tục phát triển từ những nhu cầu thực tế — vừa làm công cụ cho bản thân, vừa học cách xây dựng phần mềm.',
    explore: 'Khám phá microSched', source: 'Xem mã nguồn', signIn: 'Đăng nhập', open: 'Vào ứng dụng', checking: 'Đang kiểm tra…', retry: 'Thử lại', unknown: 'Chưa kiểm tra được phiên đăng nhập.',
    access: 'Bản triển khai cá nhân · Đăng nhập dành cho tài khoản được cấp quyền.',
    caption: 'Ảnh chụp ứng dụng với dữ liệu minh họa.',
    imageAlt: 'Giao diện microSched với các công việc và checklist mẫu, trên laptop hoặc điện thoại.',
    everyday: 'Trong một ngày dùng microSched',
    features: [
      ['Công việc, từng bước một', 'Chia việc thành checklist, đặt hạn và sắp xếp lại khi kế hoạch thay đổi.'],
      ['Ghi lại để quay lại sau', 'Giữ ghi chú, ý tưởng và những danh sách cần dùng trong ngày.'],
      ['Nhìn lịch, sắp xếp việc', 'Đưa lịch vào ứng dụng, xem các buổi sắp tới và dời việc cho phù hợp.'],
      ['Theo dõi những điều cần thiết', 'Ghi nhanh thói quen, chi tiêu và các khoản thuê bao cần gia hạn.'],
    ],
    journeyLabel: 'HÀNH TRÌNH', journeyTitle: 'Bắt đầu từ một công cụ nhỏ.',
    journeyIntro: 'Ý tưởng xuyên suốt vẫn giản dị: có một công cụ phù hợp hơn với việc học và cuộc sống. Mỗi phiên bản mở ra thêm một điều để học.',
    chapters: [
      ['01', 'C++ · Dòng lệnh', 'Những bước đầu', 'Một chương trình nhỏ, những lần tự sửa code và tập làm quen với Git.'],
      ['02', 'Python · Flet', 'Thử sức với AI', 'Từ những vòng prompt đến một ứng dụng desktop dùng được trong thực tế.'],
      ['03', 'microSched · Web', 'Tiếp tục làm bài bản hơn', 'Thiết kế, triển khai và cải tiến một ứng dụng đang được dùng hằng ngày.'],
    ],
    methodLabel: 'CÁCH DỰ ÁN ĐƯỢC PHÁT TRIỂN', methodTitle: 'Xây ứng dụng. Học cả cách làm.',
    methodBody: 'microSched cũng là nơi Hưng học harness engineering: giữ quyền quyết định về sản phẩm, giao phạm vi rõ ràng cho AI agents, dùng review độc lập và kiểm thử để kiểm tra kết quả, rồi lưu lại những quyết định quan trọng. Cách làm tiếp tục thay đổi cùng công cụ và trải nghiệm thực tế.',
    methodSteps: ['Làm rõ điều cần xây', 'Thực hiện trong phạm vi', 'Review và kiểm thử', 'Giữ lại điều đã học'],
    stack: 'React · FastAPI · PostgreSQL',
    futureLabel: 'NHỮNG HƯỚNG ĐANG MỞ', futureTitle: 'Từ màn hình, đến những điều gần gũi hơn.', futureStatus: 'Đang tìm hiểu và thiết kế',
    futureIntro: 'microSched là điểm bắt đầu cho ba dự án kết nối việc học với những nhu cầu ngoài đời.',
    futures: [
      ['Mimi', 'Trợ lý ngay trong ứng dụng', 'Làm việc với task, note, tracker và tài liệu; thực hiện thao tác với bước phê duyệt phù hợp.'],
      ['microLink', 'Nối coding agent với microSched', 'Kết nối qua MCP từ môi trường đang dùng, hiện là Codex, để đọc và cập nhật dữ liệu qua các công cụ có phạm vi rõ ràng.'],
      ['miGarden', 'Một góc ban công, một bài toán IoT', 'Theo dõi từng chậu hoa và hướng tới điều khiển tưới từ microSched. Dự kiến bắt đầu bằng vài chậu, rồi từng bước giải quyết các khó khăn về cảm biến, mạng và điều khiển tưới.'],
    ],
    ambition: 'Mục tiêu là làm ra những phiên bản đầu tiên thật chỉn chu trong kỳ học này, rồi tiếp tục phát triển sau môn học. Xa hơn, nếu miGarden thành công, Mimi có thể hỗ trợ từ gợi ý chăm hoa đến thực hiện yêu cầu tưới đã được duyệt.',
    footerTitle: 'Mã nguồn mở. Câu chuyện vẫn tiếp tục.',
    footerText: 'Repository có hướng dẫn chạy và tài liệu kỹ thuật để bạn tìm hiểu hoặc tự triển khai một bản cho mình.',
    creator: 'Người đứng sau dự án', creatorNote: 'Nguyễn Hải Hưng · Sinh viên PTIT, đang học AI engineering',
    qa: 'Preview local · Dữ liệu mẫu', qaOpen: 'Vào app với dữ liệu mẫu',
  },
  en: {
    eyebrow: 'A PERSONAL PROJECT, STILL GROWING',
    heading: <>Everyday life, in a <em>personal app.</em></>,
    intro: 'Tasks, notes, calendars and things worth keeping track of. Hưng uses microSched day to day and keeps building it around real needs — both to make a tool that fits and to learn how to build software.',
    explore: 'Explore microSched', source: 'View source', signIn: 'Sign in', open: 'Open app', checking: 'Checking session…', retry: 'Try again', unknown: 'Unable to check your app session.',
    access: 'Personal deployment · Sign-in is limited to authorized accounts.',
    caption: 'App screenshot with sample data.',
    imageAlt: 'The microSched interface with sample tasks and checklists on a laptop or phone.',
    everyday: 'A day with microSched',
    features: [
      ['Work, one step at a time', 'Break tasks into checklists, set deadlines and rearrange them when plans change.'],
      ['Keep it for later', 'Save notes, ideas and the lists you return to throughout the day.'],
      ['See the calendar, plan the work', 'Bring calendars into the app, check upcoming events and reschedule tasks.'],
      ['Keep track of what matters', 'Log habits and spending, and keep an eye on subscriptions and renewals.'],
    ],
    journeyLabel: 'THE JOURNEY', journeyTitle: 'It started with a small tool.',
    journeyIntro: 'The idea has stayed simple: a tool that fits studying and everyday life a little better. Each version brought something new to learn.',
    chapters: [
      ['01', 'C++ · Command line', 'The first steps', 'A small program, learning to edit code and getting familiar with Git.'],
      ['02', 'Python · Flet', 'Experimenting with AI', 'From rounds of prompting to a desktop app that worked in everyday life.'],
      ['03', 'microSched · Web', 'Building more deliberately', 'Designing, deploying and improving an app that is used day to day.'],
    ],
    methodLabel: 'HOW THE PROJECT IS BUILT', methodTitle: 'Building an app. Learning how to build.',
    methodBody: 'microSched is also where Hưng learns harness engineering: setting the product direction, giving AI agents a clear scope, using independent reviews and tests to check results, and preserving important decisions. The process keeps evolving with the tools and practical experience.',
    methodSteps: ['Clarify the goal', 'Work within scope', 'Review and test', 'Keep what was learned'],
    stack: 'React · FastAPI · PostgreSQL',
    futureLabel: 'WHAT COMES NEXT', futureTitle: 'Beyond the screen, closer to everyday life.', futureStatus: 'Being explored and designed',
    futureIntro: 'microSched is a starting point for three projects connecting coursework with real-world needs.',
    futures: [
      ['Mimi', 'An assistant inside the app', 'Working with tasks, notes, trackers and documents, and carrying out actions with appropriate approval.'],
      ['microLink', 'Connecting coding agents to microSched', 'An MCP connection from the coding-agent environment, currently Codex, with scoped tools for reading and updating app data.'],
      ['miGarden', 'A balcony garden meets IoT', 'Per-pot flower monitoring and, eventually, watering controls in microSched. The plan is to start with a few pots and work through challenges with sensors, networks and watering controls.'],
    ],
    ambition: 'The goal is to build solid first versions this semester and keep developing them beyond the coursework. Further ahead, if miGarden succeeds, Mimi could help with flower care, from suggestions to carrying out approved watering requests.',
    footerTitle: 'Open source. An ongoing story.',
    footerText: 'The repository includes setup instructions and technical documentation to explore or self-host the app.',
    creator: 'About the creator', creatorNote: 'Nguyễn Hải Hưng · PTIT student, learning AI engineering',
    qa: 'Local preview · Sample data', qaOpen: 'Open app with sample data',
  },
}

function usePublicLanguage() {
  const [language, updateLanguage] = useState<Language>(() => new URLSearchParams(window.location.search).get('lang') === 'en' ? 'en' : 'vi')
  function setLanguage(next: Language) {
    const url = new URL(window.location.href)
    if (next === 'en') url.searchParams.set('lang', 'en')
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
      <a href="/home" className="public-brand"><img src="/microsched.svg" width="28" height="28" alt="" />microSched</a>
      <Button variant="ghost" size="lg" onClick={() => setLanguage(vi ? 'en' : 'vi')}>{vi ? 'English' : 'Tiếng Việt'}</Button>
    </header>
    <main className="public-denied-main">
      <p className="public-eyebrow">microSched · {vi ? 'Bản triển khai cá nhân' : 'Personal deployment'}</p>
      <h1>{vi ? 'Chưa thể đăng nhập vào microSched' : 'Unable to sign in to microSched'}</h1>
      <p>{vi ? 'Lần đăng nhập này chưa hoàn tất. Bản microSched này được dùng riêng, chỉ dành cho tài khoản được cấp quyền. Nếu bạn có quyền truy cập, hãy quay về trang chủ để thử lại.' : 'This sign-in attempt could not be completed. This is a personal deployment, with access limited to authorized accounts. If you have access, return to the homepage to try again.'}</p>
      <p>{vi ? 'Bạn cũng có thể tìm hiểu mã nguồn và tự triển khai một bản cho mình.' : 'You can also explore the source code and host your own instance.'}</p>
      <div className="public-actions">
        <Button asChild size="lg"><a href={REPOSITORY_URL} target="_blank" rel="noopener noreferrer">{vi ? 'Xem mã nguồn' : 'View source'}<ArrowRight aria-hidden="true" /></a></Button>
        <Button asChild variant="outline" size="lg"><a href={`/home${vi ? '' : '?lang=en'}`}>{vi ? 'Về trang chủ' : 'Home'}</a></Button>
      </div>
      <a className="public-text-link" href={CREATOR_URL} target="_blank" rel="noopener noreferrer">{vi ? 'Người đứng sau dự án' : 'About the creator'} <ArrowRight aria-hidden="true" size={16} /></a>
    </main>
  </div>
}

export default function HomePage({ auth, location, onRetry }: { auth: PublicAuthState; location: string; onRetry: () => void }) {
  const { language, setLanguage } = usePublicLanguage()
  const c = copy[language]
  const featureIcons = [ListTodo, NotebookPen, CalendarDays, Activity]
  const methodIcons = [BookOpen, GitBranch, CheckCheck, Leaf]
  useEffect(() => {
    document.title = language === 'vi' ? 'microSched — Một ứng dụng riêng' : 'microSched — A personal app'
    return () => { document.title = 'microSched' }
  }, [language])
  return <div className="public-page" lang={language}>
    <a className="public-skip" href="#public-main">{language === 'vi' ? 'Đến nội dung' : 'Skip to content'}</a>
    <header className="public-header public-container">
      <a href="/home" className="public-brand" aria-label="microSched homepage"><img src="/microsched.svg" width="28" height="28" alt="" />microSched</a>
      <div className="public-header-actions">
        <Button variant="ghost" size="lg" onClick={() => setLanguage(language === 'vi' ? 'en' : 'vi')}>{language === 'vi' ? 'English' : 'Tiếng Việt'}</Button>
        {auth === 'signed-in' ? <Button asChild size="lg"><a href="/" data-testid="public-open-app">{c.open}<ArrowRight aria-hidden="true" /></a></Button>
          : auth === 'guest' ? <Button asChild size="lg"><a href={homepageLoginHref(location)} data-testid="login-link">{c.signIn}<ArrowRight aria-hidden="true" /></a></Button>
            : auth === 'checking' ? <Button disabled size="lg">{c.checking}</Button>
              : <Button variant="outline" size="lg" onClick={onRetry}>{c.retry}</Button>}
      </div>
    </header>
    <main id="public-main">
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
        <figure className="public-showcase">
          <picture>
            <source media="(max-width: 600px)" srcSet="/showcase/tasks-mobile.png" width="390" height="844" />
            <img src="/showcase/tasks-desktop.png" width="1280" height="800" alt={c.imageAlt} fetchPriority="high" />
          </picture>
          <figcaption>{c.caption}</figcaption>
        </figure>
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
        <ol className="public-journey">{c.chapters.map(([number, tech, title, body]) => <li key={number}><span className="public-chapter-number" aria-hidden="true">{number}</span><div><p className="public-tech">{tech}</p><h3>{title}</h3><p>{body}</p></div></li>)}</ol>
      </section>
      <section className="public-section public-container public-method" aria-labelledby="method-title">
        <div className="public-editorial"><div><p className="public-eyebrow">{c.methodLabel}</p><h2 id="method-title">{c.methodTitle}</h2></div><div><p>{c.methodBody}</p><p className="public-stack"><Code2 size={18} aria-hidden="true" />{c.stack}</p></div></div>
        <ol className="public-method-steps">{c.methodSteps.map((step, i) => { const Icon = methodIcons[i]; return <li key={step}><Icon aria-hidden="true" /><span>{step}</span></li> })}</ol>
      </section>
      <section className="public-future" aria-labelledby="future-title">
        <div className="public-container">
          <div className="public-editorial"><div><p className="public-eyebrow">{c.futureLabel}</p><h2 id="future-title">{c.futureTitle}</h2></div><div><p>{c.futureIntro}</p><p className="public-status"><span aria-hidden="true" />{c.futureStatus}</p></div></div>
          <div className="public-future-projects">{c.futures.map(([name, title, body]) => <article key={name}><h3>{name}</h3><div><h4>{title}</h4><p>{body}</p></div></article>)}</div>
          <p className="public-ambition">{c.ambition}</p>
        </div>
      </section>
    </main>
    <footer className="public-footer public-container">
      <div><h2>{c.footerTitle}</h2><p>{c.footerText}</p><Button asChild size="lg"><a href={REPOSITORY_URL} target="_blank" rel="noopener noreferrer">{c.source}<ArrowRight aria-hidden="true" /></a></Button></div>
      <div className="public-creator"><p className="public-eyebrow">{c.creator}</p><a href={CREATOR_URL} target="_blank" rel="noopener noreferrer">Nguyễn Hải Hưng <ArrowRight aria-hidden="true" size={20} /></a><p>{c.creatorNote}</p></div>
    </footer>
  </div>
}
