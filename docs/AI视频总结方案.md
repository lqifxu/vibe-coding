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
| 文本源 | yt-dlp 字幕 / 自动字幕；**B 站优先走开放 API 拉 AI/人工字幕**（可选 `BILI_COOKIE`）；**抖音无字幕轨时走云端 ASR** |
| 无字幕 | B 站/其它平台：友好报错；**抖音：下载音频 → 云端 OpenAI 兼容 Whisper → cues/transcript** |
| ASR | 仅云端 API（`ASR_PROVIDER=api`）；**不加载本地 Whisper / faster-whisper** |
| LLM | OpenAI 兼容（默认 DeepSeek：`LLM_BASE_URL` + `LLM_API_KEY`/`DEEPSEEK_API_KEY` + `LLM_MODEL`） |
| 持久化 | 内存 Job + TTL；总结配额独立于下载解析配额；前端 `sessionStorage` 可恢复 `job_id` |
| 入口 | 解析成功后**自动总结**（需已配置 LLM）；失败可重试 /「重新总结」；与下载左右同屏（`VideoResultSection` + `SplitResultShell`） |
| 展示约定 | `outline.start` 仅存数据；**总结摘要 / 思维导图 UI 不展示时间线** |
| 长任务 | SSE 墙钟最长约 **5 分钟**；状态不变时发 keepalive；断流后前端 **GET 轮询**；勿将「仍在处理」展示为硬失败 |
| 不做（暂） | 本地上传视频、本地 ASR 模型、笔记同步到第三方 |
| 会员 | 免费每日总结 10 次；Pro（Stripe 月度）解锁解析 + AI 总结无限次；详见 [会员与Stripe支付.md](./会员与Stripe支付.md) |

## 流程

```
用户已解析视频
  →（前端自动）POST /api/summarize { url }   # LLM 已配置时；无需再点「AI 总结」
  → 限流 + 日总结配额 → 创建 job（queued）；前端持久化 job_id
  → 后台线程：
       fetching_subtitles
         · B 站等：拉字幕轨
         · 抖音：下载媒体 → ffmpeg 抽音频 → 云端 /v1/audio/transcriptions → cues
       summarizing → LLM 流式 Markdown → 解析为 partial result + mindmap
  → 前端 EventSource GET /api/summarize/{id}/events
       · 墙钟约 5 分钟；payload 不变时 SSE comment keepalive
       · 软超时 / 断流 → GET /api/summarize/{id} 轮询（最多约 5 分钟）
  → 左右同屏：左下载信息 / 右四 Tab（总结摘要 / 字幕 / 导图 / 问答）
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
| `summary_router.py` | 总结 / meta / SSE / 问答 / **字幕下载** 路由；SSE 5 分钟墙钟 + keepalive |
| `summary_config.py` | 加载 `.env`、DeepSeek / ASR 相关键、总结配额等 |
| `summary_quota.py` | 每日总结次数（独立于下载 `limiter`） |
| `summary_jobs.py` | 内存 Job、后台线程、流式 partial 合并、mindmap |
| `subtitle_service.py` | yt-dlp + B 站 API 字幕；**抖音转 `asr_service`** |
| `asr_service.py` | 云端 OpenAI 兼容 Whisper（`/audio/transcriptions`）；无本地模型导入 |
| `bilibili_service.py` | B 站 view/playurl 解析与下载（规避部分环境 412） |
| `llm_service.py` | 流式 Markdown 总结、解析、问答、mindmap 树构建与标签清洗 |
| `demo_fixture.py` | 本地演示 URL `https://jisuxia.local/demo/ai-summary` |

### 前端（扩展，OCP）

| 文件 | 职责 |
|---|---|
| `summary/SplitResultShell.tsx` | 左右同屏布局壳（lg 双栏 / 移动端堆叠） |
| `summary/VideoResultSection.tsx` | 组合下载 `ResultPanel` + 自动总结 / 独立字幕下载 / 面板 |
| `summary/SummaryPanel.tsx` | 四 Tab：文档式摘要、字幕导出、导图全屏、问答；支持 embedded 窄栏 |
| `summary/mindmapRender.ts` | 彩色曲线导图 Canvas（自适应布局 / 清洗标签 / 高清导出） |
| `summary/subtitleExport.ts` | 前端 cues → SRT/VTT/TXT |
| `summary/useVideoSummary.ts` | metaReady、SSE/轮询、`job_id` 恢复、问答流式状态 |
| `summary/summaryApi.ts` | `/api/summary*`、`/api/subtitles`；SSE 软超时后轮询 |
| `summary/summaryTypes.ts` | 类型定义 |
| `App.tsx` | 有 `info` 时渲染 `VideoResultSection` |

## 字幕策略（B 站）

1. 优先 B 站开放 API：`x/v2/dm/view`（常含 `ai-zh`，**免登录**）→ `player/v2`（可选 Cookie）
2. 解析 `aisubtitle.hdslb.com` JSON `body[]` → cues
3. 其它平台仍可走 yt-dlp `subtitles` / `automatic_captions`

## 抖音 ASR（云端）

抖音无官方字幕轨。总结链路：

1. `douyin_service` 解析并下载媒体  
2. `ffmpeg` 提取单声道 16kHz 音频（可截断，见 `ASR_MAX_DURATION_SEC`）  
3. `POST {ASR_BASE_URL}/audio/transcriptions`（OpenAI 兼容；如 SiliconFlow `FunAudioLLM/SenseVoiceSmall`）  
4. 得到 `cues` / transcript → 既有 LLM 总结  

未配置 `ASR_API_KEY` 时返回明确 503（「未配置云端 ASR」），**不会**尝试下载本地模型。

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
| `ASR_PROVIDER` | `api` | 仅支持 `api`；`local` 会明确报错 |
| `ASR_BASE_URL` | （示例见 `.env.example`） | OpenAI 兼容网关，如 `https://api.siliconflow.cn/v1` |
| `ASR_API_KEY` | 空 | 抖音总结必填；勿提交真实 Key |
| `ASR_MODEL` | `whisper-1` | 如 SiliconFlow：`FunAudioLLM/SenseVoiceSmall` |
| `ASR_TIMEOUT_SEC` | `120` | 单次转写 HTTP 超时 |
| `ASR_MAX_DURATION_SEC` | `1200` | 过长视频只转写前 N 秒 |

参考：`backend/.env.example`。健康检查 `GET /api/health` 含 `asr` / `asr_api` / `asr_provider`。

## UI 行为摘要

- **左右同屏**：解析结果左栏为封面 / 标题 / 清晰度下载 / 字幕；右栏为 AI 总结四 Tab（`lg+` 并排，移动端上下堆叠）
- **自动总结**：`/api/summary/meta` 就绪且 `llm_configured` 后自动启动；失败展示原因 +「重试」；可「重新总结」
- 总结中：SSE 推送结构化 `result`；抖音 ASR 可能数分钟，前端继续等待/轮询，不误报「等待超时」
- 刷新后可按 `sessionStorage` 中的 `job_id` 恢复进行中或已完成的任务
- 「复制 Markdown」导出干净文本（无时间戳、无原始 MD 噪声）
- 拉到字幕后即可切换「字幕文本」，并可导出 SRT/VTT/TXT
- 解析结果区可独立「下载字幕」（不触发总结、不扣总结配额）
- 大纲出现后生成彩色思维导图；支持全屏缩放拖拽与 2× 高清 PNG 下载
- 「AI 问答」在 transcript 就绪后可用；支持快捷问题与流式回复

## 本地演示与自测

- 演示 URL：`https://jisuxia.local/demo/ai-summary`（内置字幕，不依赖外网平台）
- 真实 B 站用例：如带 AI 字幕的公开视频（例如学习路线类 BV）
- 抖音：配置 `ASR_*` 后，用含 `modal_id=` 或 `/video/{id}` 的链接做总结验收

```bash
cd backend
.venv\Scripts\python.exe tests\test_subtitle_parse.py
.venv\Scripts\python.exe tests\test_summary_job.py
# 服务器侧连通性（勿打印 Key；日志仅 ASCII）
.venv\Scripts\python.exe scripts\verify_asr_api.py
```

## 后续可选

- ~~抖音云端 ASR~~（已实现：OpenAI 兼容 `/audio/transcriptions`）
- 其它无字幕平台的 ASR 扩展
- 问答多轮会话持久化
- 导图主题 / 导出 SVG / `.xmind`
- ~~与 Pro 会员配额、支付打通~~（已实现：Pro 解析 + 总结无限）
