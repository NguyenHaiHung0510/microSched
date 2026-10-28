import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/** Model prose is untrusted: no raw HTML or automatic remote image requests. */
export function MimiMessageText({ text }: { text: string }) {
  return <div className="min-w-0 break-words text-sm leading-relaxed [&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:my-1 [&_blockquote]:border-l-2 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-muted [&_pre]:p-3 [&_code]:break-all [&_h1]:font-bold [&_h2]:font-bold [&_h3]:font-bold [&_h1]:my-3 [&_h2]:my-3 [&_h3]:my-2">
    <Markdown skipHtml remarkPlugins={[remarkGfm]} components={{
      img: ({ alt }) => <span className="text-muted-foreground">{alt ? `[Ảnh: ${alt}]` : '[Ảnh không tự tải]'}</span>,
      a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2">{children}</a>,
      table: ({ children }) => <div className="my-3 max-w-full overflow-x-auto"><table className="w-full border-collapse text-left text-sm">{children}</table></div>,
      th: ({ children }) => <th className="border-b p-2 font-semibold">{children}</th>,
      td: ({ children }) => <td className="border-b p-2 align-top">{children}</td>,
      input: ({ checked }) => <span role="img" aria-label={checked ? 'Đã xong' : 'Chưa xong'}>{checked ? '☑' : '☐'}</span>,
    }}>{text}</Markdown>
  </div>
}
