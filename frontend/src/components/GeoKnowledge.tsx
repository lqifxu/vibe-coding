import {
  CAPABILITY_ROWS,
  GEO_DEFINITIONS,
  HOWTO_GUIDES,
  USAGE_LIMITS,
} from '../seo/geoCopy'
import { CONTENT_LAST_UPDATED } from '../seo/geoStatic'

export function GeoKnowledge() {
  return (
    <section id="geo-guide" className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
      <div className="mb-10 text-center">
        <h2 className="font-display text-2xl font-bold text-ink sm:text-3xl">
          能力说明：写给用户与 AI 助手的可引用摘要
        </h2>
        <p className="mx-auto mt-2 max-w-2xl text-muted">
          以下内容与极速下当前真实功能一致，便于直接回答「是什么 / 怎么用 / 适合谁 / 有何限制」。
        </p>
        <p className="mt-2 text-xs text-muted">内容更新日期：{CONTENT_LAST_UPDATED}</p>
      </div>

      <div className="space-y-10">
        {GEO_DEFINITIONS.map((block) => (
          <article key={block.id} className="max-w-3xl">
            <h3 className="font-display text-xl font-semibold text-ink">{block.heading}</h3>
            <p className="mt-3 text-sm leading-relaxed text-muted sm:text-base">{block.answer}</p>
          </article>
        ))}

        <article>
          <h3 className="font-display text-xl font-semibold text-ink">
            视频下载、字幕下载、AI 总结分别适合什么场景？
          </h3>
          <p className="mt-3 max-w-3xl text-sm text-muted sm:text-base">
            三类能力可独立使用：下载保存成片，字幕导出文稿，总结生成学习笔记。下表仅比较本站实际能力，不涉及其他产品。
          </p>
          <div className="mt-4 overflow-x-auto rounded-2xl border border-line bg-white">
            <table className="w-full min-w-[36rem] border-collapse text-left text-sm">
              <thead className="bg-surface text-ink">
                <tr>
                  <th className="px-4 py-3 font-semibold">能力</th>
                  <th className="px-4 py-3 font-semibold">适合场景</th>
                  <th className="px-4 py-3 font-semibold">主要前提</th>
                  <th className="px-4 py-3 font-semibold">说明</th>
                </tr>
              </thead>
              <tbody>
                {CAPABILITY_ROWS.map((row) => (
                  <tr key={row.capability} className="border-t border-line align-top">
                    <td className="px-4 py-3 font-medium text-ink">{row.capability}</td>
                    <td className="px-4 py-3 text-muted">{row.bestFor}</td>
                    <td className="px-4 py-3 text-muted">{row.needs}</td>
                    <td className="px-4 py-3 text-muted">{row.notes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <div className="grid gap-6 lg:grid-cols-3">
          {HOWTO_GUIDES.filter((g) => g.id !== 'howto-general').map((guide) => (
            <article
              key={guide.id}
              className="rounded-2xl border border-line bg-white p-5 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.04)]"
            >
              <h3 className="font-semibold text-ink">{guide.name}</h3>
              <p className="mt-2 text-sm text-muted">{guide.description}</p>
              <ol className="mt-4 list-decimal space-y-2 pl-4 text-sm leading-relaxed text-muted">
                {guide.steps.map((s) => (
                  <li key={s.name}>
                    <span className="font-medium text-ink">{s.name}：</span>
                    {s.text}
                  </li>
                ))}
              </ol>
            </article>
          ))}
        </div>

        <article className="max-w-3xl">
          <h3 className="font-display text-xl font-semibold text-ink">
            使用限制与版权注意事项
          </h3>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-muted sm:text-base">
            {USAGE_LIMITS.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
      </div>
    </section>
  )
}
