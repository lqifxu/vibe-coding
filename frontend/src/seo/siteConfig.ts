/** 站点 SEO 配置：域名统一走 VITE_SITE_URL，上线后在 .env 替换为正式 https 域名 */

function normalizeSiteUrl(raw: string): string {
  return raw.replace(/\/+$/, '')
}

export const SITE_URL = normalizeSiteUrl(
  import.meta.env.VITE_SITE_URL || 'http://localhost:5173',
)

export const SITE_NAME = '极速下'

export const SITE_TITLE = '极速下 - 万能视频下载与AI视频总结'

export const SITE_DESCRIPTION =
  '极速下是免费的视频下载与 AI 视频总结工具：支持视频链接解析、B站视频下载、抖音视频下载、视频字幕下载，以及 AI 视频总结与思维导图，手机电脑均可使用。'

/** 面向百度等仍参考 keywords 的搜索引擎；Google 基本忽略 */
export const SITE_KEYWORDS = [
  '视频下载',
  '视频链接解析',
  'B站视频下载',
  '抖音视频下载',
  '视频字幕下载',
  'AI视频总结',
  '视频总结工具',
  '极速下',
].join(',')

export const SITE_OG_IMAGE = `${SITE_URL}/og-image.svg`
