# 极速下 — 万能视频下载网站

粘贴视频链接或分享口令 → 解析清晰度 → 下载到本地（手机 / 电脑均可）。  
同页支持 **AI 视频总结**（字幕 → 流式摘要 / 大纲 / 要点 / 总结 + 字幕文本 + 思维导图图片 + AI 问答）。

下载引擎基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp)；抖音走独立无 Cookie 分享页解析。无数据库。

更完整的设计取舍与验收记录见：[docs/项目总结.md](docs/项目总结.md)  
AI 总结技术细节见：[docs/AI视频总结方案.md](docs/AI视频总结方案.md)

## 功能

- 解析多平台视频信息与清晰度列表，下载到浏览器本地
- 仿 [鱼皮 AI 绘图](https://ai.codefather.cn/painting) 风格的转化型落地页
- Pro / 批量等入口占位（未接真实支付）
- **AI 视频总结**（解析结果区四个 Tab）：
  - **总结摘要**：文档式排版（视频概述、内容大纲、核心知识要点、总结；不展示时间线）
  - **字幕文本**：带时间戳的完整字幕列表，可下载 SRT / VTT / TXT
  - **思维导图**：彩色曲线导图，支持全屏缩放拖拽与 2× 高清 PNG 下载
  - **AI 问答**：基于本视频字幕上下文提问，流式回答
- **独立下载字幕**：解析结果区可直接下载字幕文件（不调 LLM、不扣总结配额）
- IP 限流 + 每日免费解析 / 总结次数（内存，重启清空）

## 环境要求

- **Python 3.10+**（推荐 3.12；可用 `backend/.venv`）
- **Node.js 18+**
- **ffmpeg**（强烈建议；高清音视频合并需要）
- **LLM 密钥**（AI 总结需要；默认对接 DeepSeek）

## 快速启动

### 1. 后端

```bash
cd backend
py -3.12 -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制并编辑环境变量（至少配置 LLM 密钥）
copy .env.example .env   # Windows
# cp .env.example .env   # macOS / Linux

uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

健康检查：<http://127.0.0.1:8001/api/health>  
总结元信息：<http://127.0.0.1:8001/api/summary/meta>

> 说明：本地开发前端代理默认指向 **8001**（见 `frontend/vite.config.ts`）。若改端口，请同步修改代理。

### 2. 配置 ffmpeg（可选但推荐）

任选其一：

- 将 ffmpeg 的 **bin 目录**路径写入 `backend/ffmpeg.path`（单行，已被 gitignore）
- 或设置环境变量 `FFMPEG_PATH` 指向 bin 目录或 `ffmpeg` 可执行文件

### 3. 前端

```bash
cd frontend
npm install --registry=https://registry.npmmirror.com
npm run dev
```

浏览器打开：<http://127.0.0.1:5173>  
开发服务器已将 `/api` 代理到后端 `8001` 端口。

## 抖音取链说明

| 可用 | 示例 |
|------|------|
| 分享口令（含链接） | 文案中带 `https://v.douyin.com/...` |
| 标准视频页 | `https://www.douyin.com/video/数字ID` |
| 网页弹窗地址 | `https://www.douyin.com/jingxuan?modal_id=数字ID` |

**不要**复制无视频 ID 的推荐页，例如 `https://www.douyin.com/?recommend=1`。  
抖音解析**无需登录、无需填写 Cookie**。抖音暂不支持 AI 总结（缺可用字幕）。

## API

### 下载核心

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | yt-dlp / ffmpeg / 免费解析配额状态 |
| POST | `/api/info` | Body `{ "url" }` → 标题、封面、清晰度 |
| POST | `/api/download` | Body `{ "url", "format_id" }` → 文件流 |

### AI 总结扩展

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/summary/meta` | `llm_configured`、每日总结配额、provider 提示 |
| POST | `/api/summarize` | Body `{ "url" }` → `{ job_id, remaining_summaries }` |
| GET | `/api/summarize/{job_id}` | 任务状态、`result`、流式 Markdown 快照 |
| GET | `/api/summarize/{job_id}/events` | **SSE** 推送任务进度（供前端流式 UI） |
| POST | `/api/summarize/{job_id}/ask` | Body `{ "question" }` → `{ answer }` |
| POST | `/api/summarize/{job_id}/ask/stream` | 问答 SSE 流式回答 |

## 配置（环境变量）

下载相关：

| 变量 | 默认 | 说明 |
|------|------|------|
| `TEMP_DIR` | `backend/temp` | 临时下载目录 |
| `MAX_DOWNLOAD_BYTES` | 524288000 (500MB) | 单文件上限 |
| `RATE_LIMIT_REQUESTS` | 30 | 窗口内请求上限 |
| `RATE_LIMIT_WINDOW_SEC` | 60 | 限流窗口秒数 |
| `MAX_CONCURRENT_DOWNLOADS` | 3 | 并发下载数 |
| `FREE_DAILY_PARSES` | 20（可按环境调高） | 每 IP 每日免费解析次数 |
| `TEMP_FILE_TTL_SEC` | 3600 | 临时目录保留时间 |
| `FFMPEG_PATH` | 空（可另用 `ffmpeg.path` 文件） | ffmpeg 目录或可执行文件路径 |

AI 总结相关（`backend/.env`，参考 `.env.example`）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `LLM_API_KEY` / `DEEPSEEK_API_KEY` | 空 | 必填才可总结 |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI 兼容地址 |
| `LLM_MODEL` | `deepseek-chat` | 模型名 |
| `FREE_DAILY_SUMMARIES` | `999`（代码默认；生产可改为 `5`） | 每 IP 每日总结次数 |
| `SUMMARY_JOB_TTL_SEC` | `3600` | Job 保留时间 |
| `MAX_SUMMARY_CHARS` | `80000` | 送入 LLM 的字幕上限 |
| `MAX_CONCURRENT_SUMMARIES` | `2` | 并发总结任务数 |
| `BILI_COOKIE` / `SESSDATA` | 空 | 可选；部分 B 站人工 CC 需登录时使用 |

## AI 视频总结用法

1. 在 `backend/.env` 配置 `LLM_API_KEY`（或 `DEEPSEEK_API_KEY`）
2. 前端解析视频后点击 **AI 总结**
3. 后端拉取字幕（yt-dlp → B 站 `dm/view` AI 字幕免登录回退等）→ **流式**生成 Markdown 笔记
4. 结果区四个 Tab：
   - 总结摘要（逐字打出）
   - 字幕文本
   - 思维导图（PNG 图片，可下载）
   - AI 问答（基于字幕）

本地演示链接（无需外网字幕）：`https://jisuxia.local/demo/ai-summary`

自测：

```bash
cd backend
.venv\Scripts\python.exe tests\test_subtitle_parse.py
.venv\Scripts\python.exe tests\test_summary_job.py
```

## 已知限制

- 部分平台风控 / 网络环境可能导致失败，失败时返回友好错误
- 未配置 ffmpeg 时，「需合并音轨」的高清格式可能失败
- 无数据库，配额为内存级粗限流，适合演示与小流量
- 大文件会占用服务器临时磁盘与带宽
- AI 总结依赖字幕：无字幕且无 AI 自动字幕时会报错（v1 不含 ASR 语音转写）
- 抖音等平台暂不支持总结
- YouTube 等在部分网络下可能超时

## 目录结构

```
backend/app/                 # FastAPI 下载核心 + 总结扩展
  main.py                    # 下载路由；include_router 挂载总结
  summary_router.py          # 总结 / SSE / 问答 API
  subtitle_service.py        # 字幕拉取与解析
  llm_service.py             # DeepSeek 等 LLM（流式总结 / 问答）
  summary_jobs.py            # 内存异步 Job
frontend/src/
  summary/                   # AI 总结 UI（OCP 组合挂载）
docs/项目总结.md
docs/AI视频总结方案.md
```

## 免责声明

仅供个人学习与合法备份。请遵守各平台 ToS 与版权法，勿用于未授权传播。
