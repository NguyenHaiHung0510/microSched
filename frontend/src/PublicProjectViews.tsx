import { useRef, useState, type ReactNode } from 'react'
import { flushSync } from 'react-dom'
import { ArrowUpRight, ChevronLeft, ChevronRight, Image, Play } from 'lucide-react'
import { MimiAvatar } from '@/components/brand'
import { Button } from '@/components/ui/button'
import { creatorIntro, homepageAssets, type PublicLanguage } from '@/public-home'

const GARDEN_REPOSITORY_URL = 'https://github.com/NguyenHaiHung0510/miGarden'

function ProjectHero({ title, children }: { title: ReactNode; children: ReactNode }) {
  return <section className="public-hero public-container public-project-hero" aria-labelledby="public-title">
    <div className="public-hero-copy">
      <h1 id="public-title">{title}</h1>
      <div className="public-hero-intro">{children}</div>
    </div>
  </section>
}

function ShowcaseImage({ src, label, unavailable }: { src: string; label: string; unavailable: string }) {
  const [failed, setFailed] = useState(false)
  return <figure className="public-evidence">
    {failed ? <div className="public-media-placeholder">
      <Image aria-hidden="true" size={24} /><p>{unavailable}</p>
    </div> : <a className="public-linked-image" href={src} target="_blank" rel="noopener noreferrer">
      <img src={src} alt={label} loading="lazy" onError={() => setFailed(true)} />
    </a>}
    <figcaption>{label}</figcaption>
  </figure>
}

export function PublicMimi({ language, docsUrl }: { language: PublicLanguage; docsUrl: string }) {
  const vi = language === 'vi'
  return <>
    <ProjectHero title={<span className="public-project-name"><span aria-hidden="true"><MimiAvatar size="lg" /></span>Mimi</span>}>
      <p>{vi ? 'Mình dùng Mimi để làm việc với các Task ngay trong microSched.' : 'I use Mimi to work with my tasks inside microSched.'}</p>
    </ProjectHero>

    <section className="public-section public-container public-mimi-case" aria-labelledby="mimi-rename-title">
      <div className="public-mimi-case-copy">
        <h2 id="mimi-rename-title">{vi ? 'Dọn lại tên Task' : 'Tidying up task titles'}</h2>
        <p>{vi
          ? 'Một trong những việc mình muốn Mimi làm từ đầu là dọn đống Task cũ. Cùng một việc mà mình đặt mấy kiểu tên. Mimi gom những tên cùng nghĩa, đưa mình xem các tên mới rồi đổi tiêu đề cho 68 Task qua ba lượt.'
          : 'One of the first things I wanted Mimi to do was tidy up my old tasks. I had used several names for the same work. Mimi grouped titles with the same meaning, showed me the new names, and renamed 68 distinct tasks in three batches.'}</p>
        <dl className="public-case-counts" aria-label={vi ? 'Số Task khác nhau đã đổi tiêu đề theo lượt' : 'Distinct tasks renamed by batch'}>
          {[36, 28, 4].map((count, index) => <div key={count}>
            <dt>{vi ? 'Lượt' : 'Batch'} {index + 1}</dt>
            <dd>{count}</dd>
          </div>)}
        </dl>
      </div>
      <ShowcaseImage src={homepageAssets.mimiFirst}
        label={vi ? 'Bảng đối chiếu tiêu đề Task trước và sau khi đổi' : 'Comparison of task titles before and after the changes'}
        unavailable={vi ? 'Không tải được ảnh bảng đối chiếu.' : 'The comparison image could not be loaded.'} />
    </section>

    <section className="public-section public-container public-mimi-case" aria-labelledby="mimi-create-title">
      <div className="public-mimi-case-copy">
        <h2 id="mimi-create-title">{vi ? 'Thêm Task ngay trong chat' : 'Adding a task in chat'}</h2>
        <p>{vi
          ? 'Có lần mình chỉ nhờ Mimi thêm việc tập bóng đá. Tạo xong, ngay trong chat đã có nút mở Task.'
          : 'Once, I asked Mimi to add a task for football practice. When it was ready, I could open the task from a button right in the chat.'}</p>
        <p className="public-case-note">{vi
          ? 'Đã kiểm chứng 2 Task được tạo, trong đó có Task tập bóng đá.'
          : 'I verified that two tasks were created, including the football practice task.'}</p>
      </div>
      <ShowcaseImage src={homepageAssets.mimiSecond}
        label={vi ? 'Kết quả trong chat với nút mở Task tập bóng đá' : 'Chat result with a button to open the football practice task'}
        unavailable={vi ? 'Không tải được ảnh kết quả trong chat.' : 'The chat result image could not be loaded.'} />
    </section>
    <div className="public-project-link-row public-container">
      <a className="public-text-link" href={docsUrl} target="_blank" rel="noopener noreferrer">
        {vi ? 'Tài liệu kỹ thuật của Mimi trên GitHub' : 'Mimi technical docs on GitHub'}<ArrowUpRight aria-hidden="true" size={16} />
      </a>
    </div>
  </>
}

const gardenClipOrder = [
  { youtubeId: 'I9efHbQY3Gw', vi: 'Demo tưới trực tiếp từ app điện thoại', en: 'Demo: watering from the mobile app' },
  { youtubeId: 'FNwqNWv7YZo', vi: 'Giới thiệu tổng quan hệ thống thực tế', en: 'A tour of the installed system' },
  { youtubeId: '9Bm-HChtbSQ', vi: 'Demo app điều khiển trên điện thoại', en: 'Demo: controls in the mobile app' },
  { youtubeId: 'GrRvuvgO6sg', vi: 'Demo nút bật/tắt local – bật', en: 'Demo: turning watering on at the local button' },
  { youtubeId: 'prA7ppVafvk', vi: 'Demo nút bật/tắt local – tắt', en: 'Demo: turning watering off at the local button' },
] as const

function GardenClips({ language }: { language: PublicLanguage }) {
  const vi = language === 'vi'
  const [selected, setSelected] = useState(0)
  const [requested, setRequested] = useState(false)
  const [posterMissing, setPosterMissing] = useState(false)
  const youtubePlayer = useRef<HTMLIFrameElement>(null)
  const clip = gardenClipOrder[selected]
  const title = clip[language]
  const { youtubeId } = clip
  const count = gardenClipOrder.length
  const activePoster = selected === 0 && !posterMissing ? homepageAssets.cabinet : undefined

  function changeClip(offset: number) {
    setRequested(false)
    setSelected(index => (index + offset + count) % count)
  }

  function playClip() {
    // Attach the player and start it within the same user gesture.
    flushSync(() => setRequested(true))
    youtubePlayer.current?.focus()
  }

  return <div className="public-clips">
    <div id="garden-video-stage" className="public-video-stage">
      {!requested && <>
        {activePoster && <img src={activePoster} alt="" onError={() => setPosterMissing(true)} />}
        <Button size="lg" type="button" className="public-video-play" onClick={playClip}>
          <Play aria-hidden="true" />{vi ? 'Phát video' : 'Play video'}
        </Button>
      </>}
      {requested && <iframe ref={youtubePlayer} src={`https://www.youtube-nocookie.com/embed/${youtubeId}?autoplay=1&playsinline=1`}
        title={title} allow="autoplay; encrypted-media; fullscreen" allowFullScreen referrerPolicy="strict-origin-when-cross-origin" />}
    </div>
    <div className="public-clip-toolbar">
      <p aria-live="polite" aria-atomic="true">
        <strong>{title}</strong><span className="public-clip-index">{selected + 1} / {count}</span>
      </p>
      <div className="public-actions">
        <Button type="button" variant="outline" size="lg" onClick={() => changeClip(-1)} aria-controls="garden-video-stage">
          <ChevronLeft aria-hidden="true" />{vi ? 'Trước' : 'Previous'}
        </Button>
        <Button type="button" variant="outline" size="lg" onClick={() => changeClip(1)} aria-controls="garden-video-stage">
          {vi ? 'Tiếp' : 'Next'}<ChevronRight aria-hidden="true" />
        </Button>
        <a className="public-text-link" href={`https://www.youtube.com/shorts/${youtubeId}`}
          target="_blank" rel="noopener noreferrer">
          {vi ? 'Mở trên YouTube' : 'Open on YouTube'}<ArrowUpRight aria-hidden="true" size={16} />
        </a>
      </div>
    </div>
  </div>
}

export function PublicGarden({ language }: { language: PublicLanguage }) {
  const vi = language === 'vi'
  const balconyImageUnavailable = vi ? 'Chưa có ảnh.' : 'Image unavailable.'
  return <>
    <ProjectHero title="miGarden">
      <p>{vi ? 'Mình làm miGarden để theo dõi và tưới cây ngoài ban công.' : 'I’m building miGarden to monitor and water the plants on my balcony.'}</p>
      <p>{vi
        ? 'Phần IoT ở Khu A đã xong. Nhà mình đang sửa. Sau khi sửa xong, việc còn lại là đi ống nước quanh lan can tới các chậu cây.'
        : 'The IoT work for Zone A is done. My house is being renovated. Afterward, all that’s left is to run the water line along the railing to the plants.'}</p>
    </ProjectHero>

    <section className="public-section public-container" aria-labelledby="garden-zone-title">
      <h2 id="garden-zone-title">{vi ? 'Khu A' : 'Zone A'}</h2>
      <div className="public-garden-photos">
        <ShowcaseImage src={homepageAssets.cabinet}
          label={vi ? 'Tủ điều khiển Khu A' : 'Zone A controller cabinet'}
          unavailable={vi ? 'Không tải được ảnh tủ điều khiển.' : 'The cabinet photo could not be loaded.'} />
        <ShowcaseImage src={homepageAssets.garden}
          label={vi ? 'Trạng thái và biểu đồ Khu A' : 'Zone A status and charts'}
          unavailable={vi ? 'Không tải được ảnh trạng thái và biểu đồ.' : 'The status and charts image could not be loaded.'} />
      </div>
    </section>

    <section className="public-section public-container" aria-labelledby="garden-video-title">
      <h2 id="garden-video-title">{vi ? 'Video miGarden' : 'miGarden videos'}</h2>
      <GardenClips language={language} />
    </section>

    <section className="public-section public-container" aria-labelledby="garden-balcony-title">
      <h2 id="garden-balcony-title">{vi ? 'Ban công' : 'The balcony'}</h2>
      <div className="public-balcony-equation">
        <ShowcaseImage src={homepageAssets.balconyOriginal}
          label={vi ? 'Ban công hiện tại' : 'My balcony now'} unavailable={balconyImageUnavailable} />
        <span className="public-balcony-operator">
          <span aria-hidden="true">+</span><span className="sr-only">{vi ? 'cộng' : 'plus'}</span>
        </span>
        <ShowcaseImage src={homepageAssets.balconyKit}
          label={vi ? 'Ảnh minh họa bộ ống của Ecoteway.' : 'Illustration of the tubing kit by Ecoteway.'} unavailable={balconyImageUnavailable} />
        <span className="public-balcony-operator public-balcony-equals">
          <span aria-hidden="true">=</span><span className="sr-only">{vi ? 'bằng' : 'equals'}</span>
        </span>
        <ShowcaseImage src={homepageAssets.balconySketch}
          label={vi ? 'Mình vẽ thử' : 'My rough sketch'} unavailable={balconyImageUnavailable} />
      </div>
      <p className="public-balcony-note">{vi
        ? 'Đường màu xanh là chỗ mình tính đi ống dọc lan can tới các chậu cây dự định đặt ở đó.'
        : 'The blue line shows where I plan to run the pipe along the railing to the pots I’ll put there.'}</p>
    </section>

    <div className="public-project-link-row public-container">
      <a className="public-text-link" href={GARDEN_REPOSITORY_URL} target="_blank" rel="noopener noreferrer">
        {vi ? 'Mã nguồn miGarden trên GitHub' : 'miGarden source on GitHub'}<ArrowUpRight aria-hidden="true" size={16} />
      </a>
    </div>
  </>
}

export function PublicAbout({ language, creatorUrl }: { language: PublicLanguage; creatorUrl: string }) {
  const vi = language === 'vi'
  return <>
    <ProjectHero title={vi ? 'Về mình' : 'About me'}>
      <p>{creatorIntro[language]}</p>
      <p>{vi
        ? 'Mình bắt đầu microSched bằng một chương trình dòng lệnh C++, thử làm bản desktop bằng Python và Flet, rồi đưa nó lên web. Mỗi lần làm lại, mình học thêm về cách xây phần mềm và kiểm tra kết quả khi làm việc cùng AI agents.'
        : 'I started microSched as a C++ command-line program, tried building a desktop version with Python and Flet, then brought it to the web. Each version taught me more about building software and checking the work I do with AI agents.'}</p>
    </ProjectHero>
    <section className="public-section public-container public-editorial" aria-labelledby="about-profile-title">
      <div>
        <h2 id="about-profile-title">Nguyễn Hải Hưng</h2>
        <p>{vi
          ? 'Mục này mình viết sau. Trong lúc đó ghé GitHub của mình nhé.'
          : 'I’ll write more here later. In the meantime, come say hi on GitHub.'}</p>
        <a className="public-text-link" href={creatorUrl} target="_blank" rel="noopener noreferrer">
          {vi ? 'Ghé GitHub của mình' : 'Visit my GitHub profile'}<ArrowUpRight aria-hidden="true" size={16} />
        </a>
      </div>
      <a className="public-linked-image" href={creatorUrl} target="_blank" rel="noopener noreferrer">
        <img src="/showcase/creator-preview.png" width="846" height="520" loading="lazy"
          alt={vi ? 'Phần mở đầu README giới thiệu của Hưng trên GitHub' : 'The opening of Hưng’s GitHub profile README'} />
      </a>
    </section>
  </>
}
