# AI 视频总结 — 技术方案

> 下载站同页能力：字幕优先 → LLM 流式笔记 → 四 Tab 展示（摘要 / 字幕 / 导图 / 问答）。  
> 下载核心保持 OCP：总结以独立 router / `frontend/src/summary` 扩展挂载，不侵入下载主流程。

## 产品能力（当前）

| Tab | 能力 |
|---|---|
| 总结摘要 | SSE 推送结构化字段；前端 **文档式排版**（蓝序号 / 嵌套要点）。结构固定：视频概述 / 内容大纲 / 核心知识要点 / 总结。**不展示时间戳与原始 Markdown 符号** |
| 字幕文本 | 展示带时间戳的 `cues` 列表（或纯文本 transcript）；可下载 **SRT / VTT / TXT** |
| 思维导图 | 大纲 + 要点生成树；**彩色曲线分支 Canvas**；窄栏预览 + **弹层全屏（缩放/拖拽）** + **2× 高清 PNG**。节点文案清洗时间戳与 `**` |
| AI 问答 | 基于本 Job 字幕上下文提问；支持整段回答与 SSE 流式回答 |

独立能力（不依赖 AI 总结）：

| 入口 | 能力 |
|---|---|
| 解析结果区「下载字幕」 | `POST /api/subtitles` 拉取字幕并下载文件；**不调 LLM、不扣总结配额** |

## 边界

| 项 | 当前决定 |
|---|---|
| 文本源 | yt-dlp 字幕 / 自动字幕；**B 站优先走 `x/v2/dm/view` 拉 AI 字幕（通常免登录）**；可选 `BILI_COOKIE` |
| 无字幕 | 友好报错；**不含 ASR** |
| LLM | OpenAI 兼容（默认 DeepSeek：`LLM_BASE_URL` + `LLM_API_KEY`/`DEEPSEEK_API_KEY` + `LLM_MODEL`） |
| 持久化 | 内存 Job + TTL；总结配额独立于下载解析配额 |
| 入口 | 解析结果区「AI 总结」；与下载同页（`VideoResultSection` 组合） |
| 展示约定 | `outline.start` 仅存数据；**总结摘要 / 思维导图 UI 不展示时间线** |
| 不做（暂） | 本地上传视频、笔记同步到第三方、真实支付解锁 |

## 流程

```
用户已解析视频
  → POST /api/summarize { url }
  → 限流 + 日总结配额 → 创建 job（queued）
  → 后台线程：
       fetching_subtitles → 写入 cues / transcript（前端字幕 Tab 即可用）
       summarizing → LLM 流式 Markdown → 解析为 partial result + mindmap
  → 前端 EventSource GET /api/summarize/{id}/events（失败时可降级轮询 status）
  → 总结摘要按结构化字段渲染；完成后导图 PNG、问答可用
  → POST /api/summarize/{id}/ask[/stream] 基于字幕问答

可选（不跑总结）：
  → POST /api/subtitles { url, format } → SRT/VTT/TXT 附件下载
```

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/summary/meta` | `{ llm_configured, free_daily_summaries, provider_hint }` |
| POST | `/api/summarize` | Body `{ "url" }` → `{ job_id, remaining_summaries }` |
| POST | `/api/subtitles` | Body `{ "url", "format": "srt\|vtt\|txt" }` → 字幕附件（无 LLM / 不扣总结配额） |
| GET | `/api/summarize/{job_id}` | 状态快照（含 `result`、`stream_markdown`） |
| GET | `/api/summarize/{job_id}/events` | SSE：`update` / `end` / `error` |
| POST | `/api/summarize/{job_id}/ask` | Body `{ "question" }` → `{ answer }` |
| POST | `/api/summarize/{job_id}/ask/stream` | SSE：`{ delta }` … `{ done: true }` |

`status`: `queued` | `running` | `done` | `failed`  
`stage`（running 时）: `fetching_subtitles` | `summarizing`

### `result` 结构（当前）

```json
{
  "title": "视频标题",
  "source": "manual|auto",
  "language": "ai-zh",
  "webpage_url": "https://...",
  "overview": "视频概述段落",
  "outline": [
    {
      "start": "00:00",
      "start_sec": 0,
      "title": "章节标题（不含时间戳）",
      "points": [{ "label": "小标题", "text": "内容" }]
    }
  ],
  "highlights": [{ "title": "要点标题", "text": "一句解释" }],
  "conclusion": "总结段落",
  "cues": [{ "start_sec": 0, "start": "00:00", "text": "字幕句" }],
  "transcript": "[00:00] …",
  "mindmap": {
    "name": "根节点",
    "children": [{ "name": "分支", "children": [{ "name": "叶子", "children": [] }] }]
  },
  "stream_markdown": "## 视频概述\n…",
  "summary": "（legacy，同 overview）",
  "chapters": []
}
```

后端在归一化时保证四个正文模块均有实质内容（模型缺字段时会补全兜底）；标题清洗 Markdown 与时间戳。

## 模块划分

### 后端（扩展，OCP）

| 文件 | 职责 |
|---|---|
| `summary_router.py` | 总结 / meta / SSE / 问答 / **字幕下载** 路由；`main.py` 仅 `include_router` |
| `summary_config.py` | 加载 `.env`、DeepSeek 默认、总结配额等 |
| `summary_quota.py` | 每日总结次数（独立于下载 `limiter`） |
| `summary_jobs.py` | 内存 Job、后台线程、流式 partial 合并、mindmap |
| `subtitle_service.py` | yt-dlp + B 站 view/player/dm 回退、VTT/JSON 解析、`cues_to_srt/vtt` |
| `llm_service.py` | 流式 Markdown 总结、解析、问答、mindmap 树构建与标签清洗 |
| `demo_fixture.py` | 本地演示 URL `https://jisuxia.local/demo/ai-summary` |

### 前端（扩展，OCP）

| 文件 | 职责 |
|---|---|
| `summary/VideoResultSection.tsx` | 组合下载 `ResultPanel` + 总结入口 / 独立字幕下载 / 面板 |
| `summary/SummaryPanel.tsx` | 四 Tab：文档式摘要、字幕导出、导图全屏、问答 |
| `summary/mindmapRender.ts` | 彩色曲线导图 Canvas（自适应布局 / 清洗标签 / 高清导出） |
| `summary/subtitleExport.ts` | 前端 cues → SRT/VTT/TXT |
| `summary/useVideoSummary.ts` | SSE 订阅、问答流式状态 |
| `summary/summaryApi.ts` | `/api/summary*`、`/api/subtitles` 客户端 |
| `summary/summaryTypes.ts` | 类型定义 |
| `App.tsx` | 最少挂载：有 `info` 时渲染 `VideoResultSection` |

## 字幕策略（B 站）

1. yt-dlp `subtitles` / `automatic_captions`
2. 若无：`api.bilibili.com/x/v2/dm/view?aid=&oid=&type=1`（常含 `ai-zh` AI 字幕，**免登录**）
3. 再尝试 `player/v2`（人工 CC；可能 `need_login_subtitle`，可用 `BILI_COOKIE`）
4. 解析 `aisubtitle.hdslb.com` JSON `body[]` → cues

## LLM 输出约定

流式阶段使用 Markdown，固定四级标题顺序：

```markdown
## 视频概述
## 内容大纲
## 核心知识要点
## 总结
```

大纲章节标题**不要**附带时间戳（时间仅用于内部 `start` 字段，可从字幕推断）。  
任务结束后将 Markdown 解析并归一化为 `overview` / `outline` / `highlights` / `conclusion`，并生成 `mindmap`。

## 配置

| 变量 | 默认 | 说明 |
|---|---|---|
| `LLM_API_KEY` / `DEEPSEEK_API_KEY` | 空 | 必填 |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | |
| `LLM_MODEL` | `deepseek-chat` | |
| `FREE_DAILY_SUMMARIES` | `999` | 演示默认较高；生产建议改小 |
| `SUMMARY_JOB_TTL_SEC` | `3600` | |
| `MAX_SUMMARY_CHARS` | `80000` | |
| `MAX_CONCURRENT_SUMMARIES` | `2` | |
| `BILI_COOKIE` / `SESSDATA` | 空 | 可选登录 Cookie |

参考：`backend/.env.example`。

## UI 行为摘要

- 总结中：SSE 推送结构化 `result`；前端按章节文档式渲染（清洗时间戳与 `**`）
- 「复制 Markdown」导出干净文本（无时间戳、无原始 MD 噪声）
- 拉到字幕后即可切换「字幕文本」，并可导出 SRT/VTT/TXT
- 解析结果区可独立「下载字幕」（不触发总结、不扣总结配额）
- 大纲出现后生成彩色思维导图；支持全屏缩放拖拽与 2× 高清 PNG 下载
- 「AI 问答」在 transcript 就绪后可用；支持快捷问题与流式回复

## 本地演示与自测

- 演示 URL：`https://jisuxia.local/demo/ai-summary`（内置字幕，不依赖外网平台）
- 真实 B 站用例：如带 AI 字幕的公开视频（例如学习路线类 BV）

```bash
cd backend
.venv\Scripts\python.exe tests\test_subtitle_parse.py
.venv\Scripts\python.exe tests\test_summary_job.py
```

## 后续可选

- ASR：无字幕视频的语音转写
- 问答多轮会话持久化
- 导图主题 / 导出 SVG / `.xmind`
- 与 Pro 会员配额、支付打通
