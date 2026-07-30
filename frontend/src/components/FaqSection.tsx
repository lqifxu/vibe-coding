import { FAQ_ITEMS } from '../seo/faqData'

export function FaqSection() {
  return (
    <section id="faq" className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-16">
      <div className="mb-8 text-center">
        <h2 className="font-display text-2xl font-bold text-ink sm:text-3xl">常见问题</h2>
        <p className="mt-2 text-muted">关于视频下载、字幕下载与 AI 视频总结的真实说明</p>
      </div>
      <div className="space-y-3">
        {FAQ_ITEMS.map((item) => (
          <details
            key={item.question}
            className="group rounded-2xl border border-line bg-white px-4 py-3 open:shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)]"
          >
            <summary className="cursor-pointer list-none font-medium text-ink marker:content-none [&::-webkit-details-marker]:hidden">
              <span className="flex items-start justify-between gap-3">
                <span>{item.question}</span>
                <span
                  className="mt-0.5 shrink-0 text-muted transition group-open:rotate-45"
                  aria-hidden
                >
                  +
                </span>
              </span>
            </summary>
            <p className="mt-3 pb-1 text-sm leading-relaxed text-muted">{item.answer}</p>
          </details>
        ))}
      </div>
    </section>
  )
}
