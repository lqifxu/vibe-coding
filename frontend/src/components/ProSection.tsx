import { useState } from 'react'
import type { AuthUser } from '../auth/authApi'

const FEATURES = [
  { title: '解析无限次', desc: '免费每日 10 次；Pro 不限次', soon: false },
  { title: 'AI 总结无限次', desc: '免费每日 10 次；Pro 不限次', soon: false },
  { title: '批量下载', desc: '一次粘贴多个链接，队列自动处理', soon: true },
  { title: '字幕翻译', desc: '提取字幕并一键翻译成中文', soon: true },
]

type ModalProps = {
  open: boolean
  onClose: () => void
  user: AuthUser
  onNeedLogin: () => void
  onCheckout: () => Promise<void>
  onPortal: () => Promise<void>
}

export function ProModal({
  open,
  onClose,
  user,
  onNeedLogin,
  onCheckout,
  onPortal,
}: ModalProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!open) return null

  async function handlePrimary() {
    setError(null)
    if (!user.authenticated) {
      onClose()
      onNeedLogin()
      return
    }
    if (user.is_vip) {
      setBusy(true)
      try {
        await onPortal()
      } catch (e) {
        setError(e instanceof Error ? e.message : '打开订阅管理失败')
        setBusy(false)
      }
      return
    }
    setBusy(true)
    try {
      await onCheckout()
    } catch (e) {
      setError(e instanceof Error ? e.message : '创建支付失败')
      setBusy(false)
    }
  }

  const primaryLabel = !user.authenticated
    ? '登录后购买'
    : user.is_vip
      ? '管理订阅'
      : busy
        ? '跳转支付中…'
        : '立即升级 Pro'

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
          月度订阅，到期自动续费；可随时在「管理订阅」中取消。当前 Pro 权益：
          <strong className="font-medium text-ink">解析 + AI 总结无限次</strong>
          （免费各每日 10 次）。
        </p>
        <ul className="mt-4 space-y-2 text-sm text-ink">
          <li>· 视频解析无限次（免费每日 10 次）</li>
          <li>· AI 视频总结无限次（免费每日 10 次）</li>
          <li>· 批量下载、字幕翻译即将开放</li>
        </ul>
        {user.is_vip && (
          <p className="mt-3 rounded-xl bg-brand/5 px-3 py-2 text-sm text-brand">
            你已是 Pro 会员，权益已生效。
          </p>
        )}
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
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
            disabled={busy}
            onClick={() => void handlePrimary()}
            className="flex-1 rounded-full bg-brand py-2.5 text-sm font-medium text-white hover:bg-brand-dark disabled:opacity-60"
          >
            {primaryLabel}
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
          解析 + AI 总结无限次，升级 Pro
        </h2>
        <p className="mx-auto mt-2 max-w-xl text-muted">
          免费用户每日各 10 次；超出需升级 Pro 解锁无限配额。
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
          升级 Pro
        </button>
      </div>
    </section>
  )
}
