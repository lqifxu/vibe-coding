/** 可抽取 GEO 文案与 HowTo 步骤（与页面、JSON-LD 同源） */

export const GEO_DEFINITIONS = [
  {
    id: 'what-is-ai-summary',
    heading: '什么是 AI 视频总结工具？',
    answer:
      'AI 视频总结工具基于视频字幕或文稿，用大模型生成概述、大纲、要点与结论等结构化笔记，帮助用户更快理解长视频。极速下在「有可用字幕」且「站点已配置大模型」时提供该能力；当前不做无字幕语音转写（ASR）。',
  },
  {
    id: 'what-is-jisuxia',
    heading: '极速下是什么？',
    answer:
      '极速下是网页版视频下载与 AI 视频总结工具：粘贴链接即可解析多清晰度并下载到本地，还可导出字幕；在有字幕时于同一结果区生成总结、思维导图并支持基于字幕的问答，无需安装客户端。',
  },
] as const

export const CAPABILITY_ROWS = [
  {
    capability: '视频下载',
    bestFor: '合法个人备份、离线观看、学习存档',
    needs: '可解析的视频链接；清晰度受源站与网络影响',
    notes: '默认无需用户登录/Cookie；部分高清合并依赖 ffmpeg',
  },
  {
    capability: '字幕下载',
    bestFor: '做笔记、检索台词、整理文稿',
    needs: '视频已有字幕或自动字幕',
    notes: '导出 SRT/VTT/TXT；不调用大模型、不占总结配额',
  },
  {
    capability: 'AI 视频总结',
    bestFor: '快速抓住结构与要点、导图复习、基于内容提问',
    needs: '有字幕 + 站点已配置大模型',
    notes: '抖音无字幕时走 ASR；需配置转写能力',
  },
] as const

export type HowToGuide = {
  id: string
  name: string
  description: string
  steps: { name: string; text: string }[]
}

export const HOWTO_GUIDES: HowToGuide[] = [
  {
    id: 'howto-bilibili',
    name: '如何用极速下下载 B 站视频',
    description: '通过粘贴 B 站稿件链接完成解析，并按清晰度下载到本地。',
    steps: [
      { name: '粘贴链接', text: '在首页输入框粘贴 B 站稿件页完整链接。' },
      { name: '解析视频', text: '点击「解析视频」，查看标题、封面与可用清晰度。' },
      {
        name: '选择清晰度下载',
        text: '选择目标格式下载到本地。需合并音轨的选项依赖服务器 ffmpeg；也可优先选已含音轨的格式。',
      },
    ],
  },
  {
    id: 'howto-douyin',
    name: '如何用极速下下载抖音视频',
    description: '支持分享口令与含视频 ID 的链接，默认无需 Cookie。',
    steps: [
      {
        name: '准备可用链接',
        text: '使用分享口令（含链接）、/video/数字ID，或带 modal_id= 的地址；不要复制无 ID 的推荐页。',
      },
      { name: '解析并下载', text: '粘贴后点击解析，再选择清晰度下载。默认无需登录、无需 Cookie。' },
      {
        name: '了解总结边界',
        text: '抖音可下载；无字幕时通过语音转写生成文稿再总结（需服务器已配置 ASR）。',
      },
    ],
  },
  {
    id: 'howto-subtitles',
    name: '如何用极速下下载视频字幕',
    description: '在解析成功后导出 SRT、VTT 或 TXT 字幕文件。',
    steps: [
      { name: '先解析视频', text: '粘贴链接并成功完成视频链接解析。' },
      {
        name: '导出字幕',
        text: '在结果区使用「下载字幕」，或在总结面板字幕 Tab 选择 SRT / VTT / TXT。',
      },
      {
        name: '确认前提',
        text: '若源视频没有可用字幕则无法导出；该操作不调用大模型、不占用总结配额。',
      },
    ],
  },
  {
    id: 'howto-general',
    name: '如何用极速下完成下载与 AI 总结',
    description: '四步完成链接解析、下载、字幕与（有条件时的）AI 总结。',
    steps: [
      { name: '粘贴链接或分享口令', text: '支持完整 URL；抖音等可从分享文案中提取链接。' },
      { name: '解析视频', text: '获取标题、封面与清晰度列表；免费用户有每日次数提示。' },
      { name: '下载成片或字幕', text: '按清晰度下载视频，或独立导出字幕文件。' },
      {
        name: '查看 AI 总结',
        text: '在已配置大模型且有字幕时，可自动生成总结、导图并问答；失败可重试。',
      },
    ],
  },
]

export const USAGE_LIMITS = [
  '免费用户按日限制解析次数；若开启 AI 总结，总结次数亦按日限制，具体以页面提示与站点配置为准。',
  '免费解析与 AI 总结按自然日计数，刷新页面不会恢复次数。',
  '部分平台风控、网络环境或未配置 ffmpeg 可能导致部分清晰度失败。',
  '无可用字幕时：抖音可走 ASR 语音转写后总结；其他平台仍需源站字幕。',
  '仅供个人学习与合法备份：请遵守各平台服务条款与当地版权法规，勿用于未授权传播。',
] as const
