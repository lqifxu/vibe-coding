type Props = {
  url: string
  loading: boolean
  remaining: number | null | undefined
  onUrlChange: (v: string) => void
  onSubmit: () => void
}

export function HeroParse({ url, loading, remaining, onUrlChange, onSubmit }: Props) {
  return (
    <section id="parse" className="mx-auto max-w-3xl px-4 pb-10 pt-14 text-center sm:px-6 sm:pt-20">
      <h1 className="animate-fade-up font-display text-3xl font-bold leading-tight tracking-tight text-ink sm:text-5xl">
        <span className="block text-brand">极速下</span>
        万能视频下载与 AI 总结，一键保存到本地
      </h1>
      <p className="animate-fade-up-delay mt-4 text-base text-muted sm:text-lg">
        视频链接解析 · 抖音 / YouTube 优先 · 字幕下载 · AI 视频总结，手机电脑都能用
      </p>

      <form
        className="animate-fade-up-delay mt-8 flex flex-col gap-3 sm:flex-row sm:items-center"
        onSubmit={(e) => {
          e.preventDefault()
          onSubmit()
        }}
      >
        <div className="flex flex-1 items-center rounded-full border border-line bg-white px-4 py-2 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.06)] focus-within:border-brand/40 focus-within:ring-2 focus-within:ring-brand/15">
          <svg
            className="mr-2 h-5 w-5 shrink-0 text-muted"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden
          >
            <circle cx="11" cy="11" r="7" />
            <path d="M20 20l-3.5-3.5" />
          </svg>
          <input
            value={url}
            onChange={(e) => onUrlChange(e.target.value)}
            placeholder="推荐粘贴抖音分享口令，或 YouTube / 小红书等完整链接"
            className="w-full border-0 bg-transparent py-2 text-sm text-ink outline-none placeholder:text-muted/70 sm:text-base"
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="shrink-0 rounded-full bg-brand px-8 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-60 sm:text-base"
        >
          {loading ? (
            <span className="animate-pulse-soft">解析中…</span>
          ) : (
            '解析视频'
          )}
        </button>
      </form>

      <p className="mt-3 text-xs text-muted sm:text-sm">
        {remaining === null
          ? 'Pro · 解析无限次'
          : `免费解析 · 今日剩余 ${remaining ?? 10} 次`}
        {' · '}
        <span className="text-brand">超出请升级 Pro</span>
      </p>
      <p className="mt-2 text-xs leading-relaxed text-muted/90 sm:text-sm">
        支持 B站、抖音（分享口令 / 含视频 ID 的链接）、YouTube 等。抖音无需登录。
      </p>
    </section>
  )
}
