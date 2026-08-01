import type { AuthUser } from '../auth/authApi'

type Props = {
  user: AuthUser
  onProClick: () => void
  onLoginClick: () => void
  onLogout: () => void
  onPortal: () => void
}

export function Header({ user, onProClick, onLoginClick, onLogout, onPortal }: Props) {
  return (
    <header className="sticky top-0 z-40 border-b border-line/80 bg-white/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
        <a href="/" className="flex items-center gap-2 no-underline">
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-brand text-sm font-bold text-white shadow-sm">
            极
          </span>
          <span className="font-display text-lg font-semibold tracking-tight text-ink">
            极速下
          </span>
        </a>
        <nav className="hidden items-center gap-4 text-sm text-muted xl:flex">
          <a href="#parse" className="transition hover:text-brand">
            开始下载
          </a>
          <a href="#platforms" className="transition hover:text-brand">
            支持平台
          </a>
          <a href="#features" className="transition hover:text-brand">
            功能介绍
          </a>
          <a href="#how-it-works" className="transition hover:text-brand">
            使用流程
          </a>
          <a href="#geo-guide" className="transition hover:text-brand">
            能力说明
          </a>
          <a href="#faq" className="transition hover:text-brand">
            常见问题
          </a>
          <a href="#pro" className="transition hover:text-brand">
            Pro 能力
          </a>
        </nav>
        <div className="flex items-center gap-2">
          {user.authenticated ? (
            <>
              <span className="hidden max-w-[9rem] truncate text-xs text-muted sm:inline" title={user.email}>
                {user.email}
              </span>
              {user.is_vip ? (
                <span className="rounded-full bg-brand/10 px-2 py-0.5 text-[11px] font-semibold text-brand">
                  Pro
                </span>
              ) : null}
              {user.is_vip ? (
                <button
                  type="button"
                  onClick={onPortal}
                  className="rounded-full border border-line px-3 py-1.5 text-xs font-medium text-ink hover:border-brand/40"
                >
                  管理订阅
                </button>
              ) : (
                <button
                  type="button"
                  onClick={onProClick}
                  className="rounded-full bg-brand px-4 py-1.5 text-sm font-medium text-white transition hover:bg-brand-dark"
                >
                  升级 Pro
                </button>
              )}
              <button
                type="button"
                onClick={onLogout}
                className="rounded-full border border-line px-3 py-1.5 text-xs text-muted hover:text-ink"
              >
                退出
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={onLoginClick}
                className="rounded-full border border-line px-3 py-1.5 text-sm font-medium text-ink hover:border-brand/40"
              >
                登录
              </button>
              <button
                type="button"
                onClick={onProClick}
                className="rounded-full bg-brand px-4 py-1.5 text-sm font-medium text-white transition hover:bg-brand-dark"
              >
                升级 Pro
              </button>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
