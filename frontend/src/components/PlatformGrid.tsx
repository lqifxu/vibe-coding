const PLATFORMS = [
  {
    name: 'YouTube',
    tags: ['#4K', '#无水印', '#全球'],
    gradient: 'from-red-500/90 to-red-700',
    letter: 'YT',
  },
  {
    name: '抖音 / TikTok',
    tags: ['#竖屏', '#推荐', '#短视频'],
    gradient: 'from-slate-800 to-slate-950',
    letter: '抖',
  },
  {
    name: 'Bilibili',
    tags: ['#投稿视频', '#多清晰度', '#UP主'],
    gradient: 'from-pink-400 to-pink-600',
    letter: 'B',
  },
  {
    name: '小红书',
    tags: ['#笔记', '#生活', '#种草'],
    gradient: 'from-rose-400 to-red-500',
    letter: '红',
  },
  {
    name: 'Instagram',
    tags: ['#Reels', '#Stories'],
    gradient: 'from-fuchsia-500 via-rose-500 to-amber-400',
    letter: 'IG',
  },
  {
    name: 'Twitter / X',
    tags: ['#媒体', '#GIF'],
    gradient: 'from-sky-400 to-blue-600',
    letter: 'X',
  },
]

export function PlatformGrid() {
  return (
    <section id="platforms" className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
      <div className="mb-8 text-center">
        <h2 className="font-display text-2xl font-bold text-ink sm:text-3xl">支持主流平台视频下载</h2>
        <p className="mx-auto mt-2 max-w-2xl text-muted">
          覆盖 B站、抖音、YouTube、小红书等常见平台；个别链接若失败可换一条再试。
          是否可解析、可用清晰度与字幕，以源站实际能力为准。
        </p>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-3">
        {PLATFORMS.map((p) => (
          <article
            key={p.name}
            className="group overflow-hidden rounded-2xl border border-line bg-white shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] transition hover:-translate-y-0.5 hover:shadow-[0_12px_28px_-8px_rgba(23,119,255,0.18)]"
          >
            <div
              className={`flex h-28 items-end bg-gradient-to-br ${p.gradient} p-4 sm:h-36`}
            >
              <span className="font-display text-3xl font-bold text-white/95 drop-shadow sm:text-4xl">
                {p.letter}
              </span>
            </div>
            <div className="p-3 text-left sm:p-4">
              <h3 className="font-semibold text-ink">{p.name}</h3>
              <p className="mt-1 text-xs text-muted sm:text-sm">{p.tags.join(' · ')}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
