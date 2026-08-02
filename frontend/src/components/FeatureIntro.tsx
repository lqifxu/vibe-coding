const FEATURES = [
  {
    title: '视频链接解析与多清晰度下载',
    desc: '粘贴链接或分享口令即可完成视频链接解析，按清晰度保存到本地，手机与电脑浏览器均可使用。适合日常备份与学习存档。',
  },
  {
    title: '抖音 / YouTube 等主流平台',
    desc: '支持 B站投稿链接、抖音分享口令、YouTube、小红书等常见平台。粘贴链接即可解析多清晰度并下载。',
  },
  {
    title: '视频字幕下载',
    desc: '解析成功后可导出 SRT / VTT / TXT 字幕文件，独立于 AI 总结，不占用总结配额，方便做笔记或二次整理。',
  },
  {
    title: 'AI 视频总结与学习笔记',
    desc: '在有字幕时自动生成概述、大纲、核心要点与总结，并提供思维导图与基于字幕的问答，让长视频更快变成可复习的笔记。',
  },
]

export function FeatureIntro() {
  return (
    <section id="features" className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
      <div className="mb-8 max-w-3xl text-center sm:mx-auto sm:text-left">
        <h2 className="font-display text-2xl font-bold text-ink sm:text-3xl">
          功能介绍：下载与 AI 视频总结同页完成
        </h2>
        <p className="mt-3 text-muted">
          极速下把「视频下载」和「视频总结工具」放在同一结果区：左边保存成片与字幕，右边生成结构化学习笔记，减少来回切换。
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {FEATURES.map((f) => (
          <article
            key={f.title}
            className="rounded-2xl border border-line bg-white/90 p-5 text-left shadow-[0_4px_20px_-4px_rgba(0,0,0,0.04)]"
          >
            <h3 className="font-semibold text-ink">{f.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">{f.desc}</p>
          </article>
        ))}
      </div>
    </section>
  )
}
