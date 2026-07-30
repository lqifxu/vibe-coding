import { CONTENT_LAST_UPDATED } from '../seo/geoStatic'
import { SITE_URL } from '../seo/siteConfig'

export function Footer() {
  return (
    <footer className="border-t border-line bg-white/70">
      <div className="mx-auto max-w-6xl px-4 py-8 text-center text-xs leading-relaxed text-muted sm:px-6 sm:text-sm">
        <p>
          本站仅供个人学习与合法备份使用。请遵守各平台服务条款与当地版权法规，
          勿用于未授权的商业传播。
        </p>
        <p className="mt-2">
          下载引擎基于开源项目{' '}
          <a
            className="text-brand hover:underline"
            href="https://github.com/yt-dlp/yt-dlp"
            target="_blank"
            rel="noreferrer"
          >
            yt-dlp
          </a>
          {' · '}
          内容更新日期 {CONTENT_LAST_UPDATED}
          {' · '}
          <a className="text-brand hover:underline" href={`${SITE_URL}/llms.txt`}>
            llms.txt
          </a>
          {' · '}
          © {new Date().getFullYear()} 极速下
        </p>
      </div>
    </footer>
  )
}
