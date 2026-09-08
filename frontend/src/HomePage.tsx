import { useEffect, useState } from 'react'
import { ArrowDown, ArrowRight, Code2, Leaf, ListTodo, NotebookPen, CalendarDays, Activity, GitBranch, CheckCheck, BookOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { homepageLoginHref, type PublicAuthState } from '@/public-navigation'
import { PublicShowcase } from '@/PublicShowcase'
import './public-pages.css'

export const REPOSITORY_URL = 'https://github.com/NguyenHaiHung0510/microSched'
export const CREATOR_URL = 'https://github.com/NguyenHaiHung0510'
type Language = 'vi' | 'en'

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
    futureLabel: 'NHỮNG DỰ ĐỊNH TIẾP THEO', futureTitle: 'Những điều mình muốn làm tiếp.', futureStatus: 'Đang tìm hiểu và thiết kế',
    futureIntro: 'Mình đang thiết kế ba dự án kết nối với microSched, từ những gì đang học ở trường và những thứ muốn tự làm để dùng.',
    futures: [
      ['Mimi', 'Trợ lý trong microSched', 'Mình muốn có một trợ lý làm việc được với task, note, tracker và tài liệu ngay trong app. Mimi sẽ thực hiện thao tác trong phạm vi được cho phép, với bước xác nhận phù hợp.'],
      ['microLink', 'Kết nối coding agent với microSched', 'Mình muốn coding agent có thể đọc và cập nhật dữ liệu microSched ngay từ môi trường đang dùng, hiện là Codex. microLink sẽ kết nối hai bên qua MCP, với các công cụ có phạm vi rõ ràng.'],
      ['miGarden', 'Theo dõi và tưới hoa', 'Mình thích trồng hoa và muốn theo dõi từng chậu, rồi điều khiển tưới từ microSched. Phần cứng, kết nối chập chờn và nước khiến đây là một dự án đầy tham vọng, với không ít điều có thể hỏng. Mình muốn bắt đầu bằng một mô hình thử nghiệm nhỏ, học từ những lần thất bại và tiếp tục hoàn thiện thành một hệ thống mình có thể sử dụng và tin cậy.'],
    ],
    ambition: 'Mình muốn hoàn thành những phiên bản đầu tiên thật chỉn chu trong kỳ học này, rồi tiếp tục phát triển sau khi kết thúc môn học. Nếu miGarden làm được như dự định, mình còn mong Mimi có thể gợi ý cách chăm hoa và thực hiện yêu cầu tưới sau khi được mình duyệt.',
    footerTitle: 'Bạn muốn tìm hiểu thêm?',
    footerText: 'Mình chia sẻ mã nguồn và tài liệu kỹ thuật trên GitHub. Bạn có thể tìm hiểu cách mình xây ứng dụng hoặc làm theo hướng dẫn để tự chạy một bản.',
    creator: 'Một chút về mình', creatorNote: 'Mình là sinh viên PTIT, đang học AI engineering.',
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
    futureLabel: 'WHAT COMES NEXT', futureTitle: 'Beyond the screen, closer to everyday life.', futureStatus: 'Being explored and designed',
    futureIntro: 'I’m designing three projects around microSched, connecting what I’m learning with things I want to do in everyday life.',
    futures: [
      ['Mimi', 'An assistant inside the app', 'I’m designing an assistant to work with my tasks, notes, trackers and documents inside microSched, and carry out actions within its permissions and with appropriate confirmation.'],
      ['microLink', 'Connecting coding agents to microSched', 'I’m designing an MCP connection from the coding-agent environment I use, currently Codex, to microSched, with scoped tools for reading and updating app data.'],
      ['miGarden', 'A balcony garden meets IoT', 'I enjoy growing flowers and want to monitor individual pots and, eventually, control watering through microSched. I plan to start with a few pots and work through challenges with sensors, networks and watering controls.'],
    ],
    ambition: 'My goal is to build solid first versions this semester and keep developing them beyond the coursework. Further ahead, if miGarden succeeds, I’d love Mimi to help with flower care, from suggestions to carrying out watering requests I’ve approved.',
    footerTitle: 'Open source. An ongoing story.',
    footerText: 'I share the source code and technical documentation on GitHub so you can explore how I built the app or follow the setup instructions to run your own instance.',
    creator: 'About me', creatorNote: 'I’m a PTIT student, learning AI engineering.',
    qa: 'Local preview · Sample data', qaOpen: 'Open app with sample data',
  },
}

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
      <a href={`/home${language === 'vi' ? '?lang=vi' : ''}`} className="public-brand" aria-label={language === 'vi' ? 'Trang chủ microSched' : 'microSched homepage'}><img src="/microsched.svg" width="28" height="28" alt="" />microSched</a>
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
      <div><a className="public-repo-preview" href={REPOSITORY_URL} target="_blank" rel="noopener noreferrer" aria-label={c.source}><img src="/showcase/source-preview.png" width="838" height="600" loading="lazy" alt={language === 'vi' ? 'Một phần README của microSched trên GitHub' : 'A preview of the microSched README on GitHub'} /></a><h2>{c.footerTitle}</h2><p>{c.footerText}</p><Button asChild size="lg"><a href={REPOSITORY_URL} target="_blank" rel="noopener noreferrer">{c.source}<ArrowRight aria-hidden="true" /></a></Button></div>
      <div className="public-creator"><a className="public-profile-preview" href={CREATOR_URL} target="_blank" rel="noopener noreferrer" aria-label={c.creator}><img src="/showcase/creator-preview.png" width="846" height="520" loading="lazy" alt={language === 'vi' ? 'Phần mở đầu README giới thiệu của Hưng trên GitHub' : 'The opening of Hưng’s GitHub profile README'} /></a><p className="public-eyebrow">{c.creator}</p><a href={CREATOR_URL} target="_blank" rel="noopener noreferrer">Nguyễn Hải Hưng <ArrowRight aria-hidden="true" size={20} /></a><p>{c.creatorNote}</p></div>
    </footer>
  </div>
}
