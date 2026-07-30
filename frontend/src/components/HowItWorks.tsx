const STEPS = [
  {
    step: '01',
    title: '粘贴链接或分享口令',
    desc: '支持完整视频 URL，以及抖音等平台分享文案中的链接。系统会自动提取可解析地址。',
  },
  {
    step: '02',
    title: '一键视频链接解析',
    desc: '点击「解析视频」获取标题、封面与可用清晰度列表；免费用户有每日次数提示。',
  },
  {
    step: '03',
    title: '选择清晰度下载到本地',
    desc: '按需下载目标格式。部分需合并音轨的高清选项依赖服务器 ffmpeg；也可优先选择已含音轨的格式。',
  },
  {
    step: '04',
    title: '字幕下载与 AI 视频总结',
    desc: '可导出字幕文件；在已配置大模型且视频有字幕时，自动生成 AI 视频总结、思维导图，并可继续提问。',
  },
]

export function HowItWorks() {
  return (
    <section id="how-it-works" className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
      <div className="mb-8 text-center">
        <h2 className="font-display text-2xl font-bold text-ink sm:text-3xl">下载流程怎么走</h2>
        <p className="mt-2 text-muted">
          四步完成解析、下载、字幕与总结，无需安装客户端。B 站 / 抖音 / 字幕的分步说明见下方「能力说明」。
        </p>
      </div>
      <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map((s) => (
          <li
            key={s.step}
            className="rounded-2xl border border-line bg-white p-5 text-left shadow-[0_4px_20px_-4px_rgba(0,0,0,0.04)]"
          >
            <span className="font-display text-sm font-semibold text-brand">{s.step}</span>
            <h3 className="mt-2 font-semibold text-ink">{s.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">{s.desc}</p>
          </li>
        ))}
      </ol>
    </section>
  )
}
