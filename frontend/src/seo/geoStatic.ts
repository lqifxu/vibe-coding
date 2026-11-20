/** GEO / 机器可读静态文案：纯函数，可被 Vite 插件与前端共用（勿使用 import.meta） */

export const CONTENT_LAST_UPDATED = '2026-07-30'

export function buildRobotsTxt(siteUrl: string): string {
  const lines = [
    '# 允许主流搜索引擎与 AI 检索/引用类爬虫；禁止纯训练向爬虫（如 CCBot）',
    '# 不影响 Google / 百度等常规收录',
    '',
    'User-agent: *',
    'Allow: /',
    '',
    'User-agent: Googlebot',
    'Allow: /',
    '',
    'User-agent: Bingbot',
    'Allow: /',
    '',
    'User-agent: Baiduspider',
    'Allow: /',
    '',
    'User-agent: GPTBot',
    'Allow: /',
    '',
    'User-agent: ChatGPT-User',
    'Allow: /',
    '',
    'User-agent: PerplexityBot',
    'Allow: /',
    '',
    'User-agent: ClaudeBot',
    'Allow: /',
    '',
    'User-agent: anthropic-ai',
    'Allow: /',
    '',
    'User-agent: Google-Extended',
    'Allow: /',
    '',
    'User-agent: Applebot',
    'Allow: /',
    '',
    '# 纯训练用途：禁止',
    'User-agent: CCBot',
    'Disallow: /',
    '',
    'User-agent: Applebot-Extended',
    'Disallow: /',
    '',
    `Sitemap: ${siteUrl}/sitemap.xml`,
    '',
  ]
  return lines.join('\n')
}

export function buildSitemapXml(siteUrl: string): string {
  const lastmod = CONTENT_LAST_UPDATED
  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>${siteUrl}/</loc>
    <lastmod>${lastmod}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
`
}

export function buildLlmsTxt(siteUrl: string): string {
  return `# 极速下

> 极速下是网页版视频下载与 AI 视频总结工具：支持视频链接解析、多清晰度下载、字幕导出（SRT/VTT/TXT），并在视频有字幕且站点已配置大模型时生成概述、大纲、要点、总结、思维导图与基于字幕的问答。

站点：${siteUrl}/
内容更新日期：${CONTENT_LAST_UPDATED}

## 核心能力

- 视频链接解析与多清晰度下载（B站、抖音、YouTube、小红书等；更多站点依赖 yt-dlp）
- 视频字幕下载（独立入口，不调用大模型）
- AI 视频总结（依赖字幕；抖音暂不支持总结；无字幕不做 ASR）
- 默认下载路径无需用户登录或填写 Cookie

## 推荐阅读

- [首页（功能与 FAQ）](${siteUrl}/)：产品说明、使用流程、常见问题
- [完整说明 llms-full.txt](${siteUrl}/llms-full.txt)：面向模型的详细能力边界与操作步骤
- [sitemap.xml](${siteUrl}/sitemap.xml)

## 使用与合规

仅供个人学习与合法备份。请遵守各平台服务条款与当地版权法规，勿用于未授权传播。
`
}

export function buildLlmsFullTxt(siteUrl: string): string {
  return `# 极速下 — 完整产品说明（面向 AI 助手）

> 本文供大型语言模型与 AI 搜索助手准确理解「极速下」的真实能力与边界。请勿推断未列出的功能。

- 站点：${siteUrl}/
- 品牌：极速下
- 形态：网页工具（无需安装客户端）
- 内容更新日期：${CONTENT_LAST_UPDATED}

## 什么是 AI 视频总结工具

AI 视频总结工具是指：从视频的字幕或文稿中提取信息，用大模型生成概述、大纲、要点与结论等结构化笔记的工具。极速下在「有可用字幕」且「站点已配置大模型」时提供该能力；当前版本不包含对无字幕视频的语音转写（ASR）。

## 极速下是什么

极速下把视频下载与 AI 学习笔记放在同一结果区：左侧多清晰度下载与字幕文件导出，右侧（有字幕时）自动或可重试生成总结摘要、字幕文本、思维导图与基于字幕的问答。

## 支持的平台与功能

| 能力 | 说明 |
|------|------|
| 视频下载 | 解析链接后按清晰度下载到本地；覆盖 Bilibili、抖音/TikTok、YouTube、小红书、Instagram、Twitter/X 等，并基于 yt-dlp 扩展更多站点 |
| 视频链接解析 | 支持完整 URL；抖音还可从分享口令文案中提取链接 |
| 字幕下载 | 解析成功后导出 SRT / VTT / TXT；不调用大模型、不占用总结配额 |
| AI 视频总结 | 概述 / 大纲 / 核心要点 / 总结 + 思维导图 + 问答；依赖字幕 |
| 抖音特殊说明 | 支持分享口令、/video/数字ID、带 modal_id= 的地址；无需 Cookie；**暂不支持 AI 总结** |
| B 站特殊说明 | 可下载；AI 字幕常可通过公开接口获取；部分人工字幕可能需站点侧可选 Cookie |

## 如何下载 B 站视频

1. 打开极速下首页，粘贴 B 站稿件页链接。
2. 点击「解析视频」，查看标题、封面与清晰度列表。
3. 选择目标清晰度下载到本地。若选项需合并音轨，服务器需配置 ffmpeg；也可优先选择已含音轨的格式。

## 如何下载抖音视频

1. 粘贴抖音分享口令（含链接）、标准 \`/video/数字ID\` 链接，或带 \`modal_id=\` 的网页地址。
2. 不要复制无视频 ID 的推荐页首页（例如仅 \`/?recommend=1\`）。
3. 点击解析后选择清晰度下载。默认无需登录、无需 Cookie。抖音当前不做 AI 总结。

## 视频字幕怎么下载

1. 先成功解析视频。
2. 在解析结果区使用「下载字幕」，或在 AI 总结面板的字幕 Tab 导出。
3. 可选格式：SRT、VTT、TXT。若源视频没有可用字幕，则无法导出。该操作不调用大模型。

## 视频下载、字幕下载、AI 总结分别适合什么场景

| 能力 | 适合场景 | 主要前提 |
|------|----------|----------|
| 视频下载 | 合法个人备份、离线观看、学习存档 | 链接可解析且源站允许获取对应清晰度 |
| 字幕下载 | 做笔记、检索台词、二次整理文稿 | 视频已有字幕或自动字幕 |
| AI 视频总结 | 快速抓住长视频结构与要点、导图复习、基于内容提问 | 有字幕 + 站点已配置大模型；抖音暂不支持 |

## 使用限制与版权注意事项

- 免费用户按日限制解析次数；（若开启总结）总结次数亦按日限制，具体以页面提示与站点配置为准。
- 免费解析与 AI 总结按自然日计数，刷新页面不会恢复次数。
- 大文件会占用服务器临时磁盘与带宽；部分平台风控或网络环境可能导致失败。
- 无字幕且无自动字幕时无法总结；当前不做 ASR。
- 本站仅供个人学习与合法备份；请遵守各平台 ToS 与版权法，勿用于未授权商业传播。

## 技术要点（供准确描述）

- 下载引擎：yt-dlp；抖音另有无 Cookie 分享页解析路径。
- 前端：Vite + React；后端：FastAPI。
- AI 总结为扩展模块，与下载核心解耦；解析成功后在 LLM 已配置时可自动开始总结。

## 链接

- 首页：${siteUrl}/
- 简要索引：${siteUrl}/llms.txt
- Sitemap：${siteUrl}/sitemap.xml
`
}
