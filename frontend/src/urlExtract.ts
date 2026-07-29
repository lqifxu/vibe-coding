const PREFERRED_HOST_HINTS = [
  'v.douyin.com',
  'www.douyin.com',
  'www.iesdouyin.com',
  'douyin.com',
  'v.tiktok.com',
  'www.tiktok.com',
  'vm.tiktok.com',
  'b23.tv',
  'bilibili.com',
  'youtu.be',
  'youtube.com',
  'xiaohongshu.com',
  'xhslink.com',
  'instagram.com',
  'twitter.com',
  'x.com',
]

const URL_RE = /https?:\/\/[^\s<>"'`]+/gi
const TRAIL_PUNCT_RE = /[)\],.，。！？；：、》〉」』】]+$/g

function cleanUrl(raw: string): string {
  let u = raw.trim().replace(TRAIL_PUNCT_RE, '')
  while (u && /[.,;:!?)\]}>\"']$/.test(u)) {
    u = u.slice(0, -1)
  }
  return u
}

function hostPriority(url: string): number {
  try {
    const host = new URL(url).hostname.toLowerCase()
    const idx = PREFERRED_HOST_HINTS.findIndex(
      (h) => host === h || host.endsWith('.' + h) || host.includes(h),
    )
    return idx >= 0 ? idx : 500
  } catch {
    return 999
  }
}

/** Extract best video URL from Douyin-style share paste text. */
export function extractUrlFromText(text: string): string | null {
  const trimmed = (text || '').trim()
  if (!trimmed) return null

  if (/^https?:\/\//i.test(trimmed)) {
    const first = trimmed.split(/\s+/)[0]
    return cleanUrl(first)
  }

  const matches = trimmed.match(URL_RE)
  if (!matches?.length) return null

  const cleaned = matches
    .map(cleanUrl)
    .filter((u) => /^https?:\/\//i.test(u))
  if (!cleaned.length) return null

  cleaned.sort((a, b) => hostPriority(a) - hostPriority(b))
  return cleaned[0]
}

export const NO_URL_MESSAGE =
  '未在分享内容中找到视频链接，请复制完整分享口令（需包含 https://v.douyin.com/... ）'
