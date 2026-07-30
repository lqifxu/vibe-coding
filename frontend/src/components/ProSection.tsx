const FEATURES = [
  { title: '无限解析', desc: '告别每日次数限制，随时随地下载', soon: false },
  { title: '批量下载', desc: '一次粘贴多个链接，队列自动处理', soon: true },
  { title: '字幕翻译', desc: '提取字幕并一键翻译成中文', soon: true },
  { title: 'AI 视频总结', desc: '长视频秒变要点，学习效率翻倍', soon: false },
]

type Props = {
  open: boolean
  onClose: () => void
}

export function ProModal({ open, onClose }: Props) {
  if (!open) return null
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl animate-fade-up"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="font-display text-xl font-bold text-ink">升级极速下 Pro</h3>
        <p className="mt-2 text-sm text-muted">
          支持开发者持续更新。正式上线后，第一批用户可享专属优惠。
        </p>
        <ul className="mt-4 space-y-2 text-sm text-ink">
          <li>· 无限次数解析与更高下载并发</li>
          <li>· 批量下载队列（即将开放）</li>
          <li>· AI 视频总结已可用；字幕翻译即将开放</li>
        </ul>
        <div className="mt-6 flex gap-3">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-full border border-line py-2.5 text-sm font-medium text-ink"
          >
            以后再说
          </button>
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-full bg-brand py-2.5 text-sm font-medium text-white hover:bg-brand-dark"
          >
            已登记兴趣
          </button>
        </div>
      </div>
    </div>
  )
}

export function ProSection({ onProClick }: { onProClick: () => void }) {
  return (
    <section id="pro" className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:pb-20">
      <div className="rounded-3xl border border-brand/15 bg-gradient-to-br from-white via-white to-brand/5 px-6 py-10 text-center sm:px-12">
        <h2 className="font-display text-2xl font-bold text-ink sm:text-3xl">
          下载还不够，值得升级 Pro
        </h2>
        <p className="mx-auto mt-2 max-w-xl text-muted">
          从存档到高效学习：Pro 将下载体验与学习效率一并提升。
        </p>
        <div className="mt-8 grid gap-4 text-left sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className={`rounded-2xl border bg-white p-4 ${
                f.soon ? 'border-dashed border-line opacity-80' : 'border-line'
              }`}
            >
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-ink">{f.title}</h3>
                {f.soon && (
                  <span className="rounded-full bg-surface px-2 py-0.5 text-[10px] text-muted">
                    即将开放
                  </span>
                )}
              </div>
              <p className="mt-2 text-sm text-muted">{f.desc}</p>
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={onProClick}
          className="mt-8 rounded-full bg-brand px-8 py-3 text-sm font-semibold text-white hover:bg-brand-dark"
        >
          了解 Pro 权益
        </button>
      </div>
    </section>
  )
}
