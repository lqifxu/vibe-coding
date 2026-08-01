import { useState } from 'react'

type Mode = 'login' | 'register'

type Props = {
  open: boolean
  mode: Mode
  onModeChange: (mode: Mode) => void
  onClose: () => void
  onSubmit: (email: string, password: string, mode: Mode) => Promise<void>
}

export function AuthModal({ open, mode, onModeChange, onClose, onSubmit }: Props) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (!open) return null

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await onSubmit(email.trim(), password, mode)
      setPassword('')
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl animate-fade-up"
        onClick={(ev) => ev.stopPropagation()}
      >
        <h3 className="font-display text-xl font-bold text-ink">
          {mode === 'login' ? '登录极速下' : '注册账号'}
        </h3>
        <p className="mt-2 text-sm text-muted">
          {mode === 'login'
            ? '登录后可购买 Pro，解锁解析与 AI 总结无限次。'
            : '创建账号后即可升级 Pro（解析 + AI 总结无限次）。'}
        </p>
        <form className="mt-5 space-y-3" onSubmit={handleSubmit}>
          <label className="block text-left text-sm">
            <span className="text-muted">邮箱</span>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded-xl border border-line px-3 py-2.5 text-ink outline-none focus:border-brand"
            />
          </label>
          <label className="block text-left text-sm">
            <span className="text-muted">密码（至少 8 位）</span>
            <input
              type="password"
              required
              minLength={8}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-xl border border-line px-3 py-2.5 text-ink outline-none focus:border-brand"
            />
          </label>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-full bg-brand py-2.5 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
          >
            {busy ? '请稍候…' : mode === 'login' ? '登录' : '注册'}
          </button>
        </form>
        <p className="mt-4 text-center text-sm text-muted">
          {mode === 'login' ? (
            <>
              还没有账号？{' '}
              <button
                type="button"
                className="font-medium text-brand"
                onClick={() => {
                  setError(null)
                  onModeChange('register')
                }}
              >
                注册
              </button>
            </>
          ) : (
            <>
              已有账号？{' '}
              <button
                type="button"
                className="font-medium text-brand"
                onClick={() => {
                  setError(null)
                  onModeChange('login')
                }}
              >
                登录
              </button>
            </>
          )}
        </p>
      </div>
    </div>
  )
}
