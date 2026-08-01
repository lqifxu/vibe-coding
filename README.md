# 极速下 — 万能视频下载网站

粘贴视频链接或分享口令 → 解析清晰度 → 下载到本地（手机 / 电脑均可）。  
同页支持 **AI 视频总结**（字幕 → 流式摘要 / 大纲 / 要点 / 总结 + 字幕文本 + 思维导图图片 + AI 问答）。

下载引擎基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp)；抖音走独立无 Cookie 分享页解析。账号与 Pro 订阅使用本地 SQLite + Stripe。

更完整的设计取舍与验收记录见：[docs/项目总结.md](docs/项目总结.md)  
AI 总结技术细节见：[docs/AI视频总结方案.md](docs/AI视频总结方案.md)  
会员与 Stripe 见：[docs/会员与Stripe支付.md](docs/会员与Stripe支付.md)

## 功能

- 解析多平台视频信息与清晰度列表，下载到浏览器本地
- 仿 [鱼皮 AI 绘图](https://ai.codefather.cn/painting) 风格的转化型落地页
- **邮箱注册登录** + **Stripe 月度 Pro**（解析 + AI 总结无限次）
- 免费额度：每日解析 **10** 次、AI 总结 **10** 次（超出需升级 Pro）
- **AI 视频总结**（解析后自动总结，与下载左右同屏；四个 Tab）：
  - **总结摘要**：文档式排版（视频概述、内容大纲、核心知识要点、总结；不展示时间线）
  - **字幕文本**：带时间戳的完整字幕列表，可下载 SRT / VTT / TXT
  - **思维导图**：彩色曲线导图，支持全屏缩放拖拽与 2× 高清 PNG 下载
  - **AI 问答**：基于本视频字幕上下文提问，流式回答
- **独立下载字幕**：解析结果区可直接下载字幕文件（不调 LLM、不扣总结配额）
- IP 限流 + 每日免费解析（内存，默认 10）；AI 总结：匿名按 IP、登录免费用户按账号（默认 10）；Pro 两者均无限

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

# 复制并编辑环境变量（至少配置 LLM 密钥；测支付再配 Stripe）
copy .env.example .env   # Windows
# cp .env.example .env   # macOS / Linux

uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

健康检查：<http://127.0.0.1:8001/api/health>  
总结元信息：<http://127.0.0.1:8001/api/summary/meta>  
当前用户：<http://127.0.0.1:8001/api/auth/me>

> 说明：本地开发前端代理默认指向 **8001**（见 `frontend/vite.config.ts`）。若改端口，请同步修改代理。

测 Pro 支付时另开终端：`stripe listen --forward-to http://127.0.0.1:8001/api/billing/webhook`，步骤见 [docs/会员与Stripe支付.md](docs/会员与Stripe支付.md)。

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

### 4. SEO（上线必改）

编辑 `frontend/.env`（可参考 `frontend/.env.example`）：

```bash
VITE_SITE_URL=http://localhost:5173
```

上线改为正式 `https://你的域名` 后执行 `npm run build`。将同时更新：

- canonical / Open Graph / Twitter 卡片中的站点地址
- 构建产物 `robots.txt`、`sitemap.xml`
- JSON-LD 中的站点 URL

首页另有可抓取内容区：支持平台、功能介绍、使用流程、能力说明（GEO）、FAQ（与真实产品能力一致）。上线后请在百度站长平台 / Google Search Console 提交 `https://你的域名/sitemap.xml`。

### 5. GEO（AI 对话可引用）

构建后根路径提供：

- `/llms.txt` — 给模型的简要索引
- `/llms-full.txt` — 完整能力边界与操作步骤

`robots.txt` 允许 GPTBot、ChatGPT-User、PerplexityBot、ClaudeBot、Google-Extended、Bingbot 等检索/引用类爬虫；禁止 CCBot、Applebot-Extended 等纯训练向爬虫；不改变 Google / 百度正常抓取。

未提供公开 `pricing.md`：价格在你的 Stripe Product/Price 中配置；站点只引用 `STRIPE_PRICE_ID`。

更完整说明见 [docs/项目总结.md](docs/项目总结.md) 第 7 / 7.1 节。

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
| GET | `/api/summary/meta` | `llm_configured`、配额、`is_vip` |
| POST | `/api/summarize` | Body `{ "url" }` → `{ job_id, remaining_summaries, is_vip }`（VIP 时 remaining 为 `null`） |
| GET | `/api/summarize/{job_id}` | 任务状态、`result`、流式 Markdown 快照 |
| GET | `/api/summarize/{job_id}/events` | **SSE** 推送任务进度（供前端流式 UI） |
| POST | `/api/summarize/{job_id}/ask` | Body `{ "question" }` → `{ answer }` |
| POST | `/api/summarize/{job_id}/ask/stream` | 问答 SSE 流式回答 |

### 账号与计费

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` / `login` / `logout` | 邮箱密码会话（Cookie） |
| GET | `/api/auth/me` | 登录态、VIP、剩余总结次数 |
| POST | `/api/billing/checkout` | Stripe Checkout（月度订阅） |
| POST | `/api/billing/portal` | Stripe Customer Portal |
| POST | `/api/billing/webhook` | Stripe Webhook（验签 + 幂等） |

## 配置（环境变量）

下载相关：

| 变量 | 默认 | 说明 |
|------|------|------|
| `TEMP_DIR` | `backend/temp` | 临时下载目录 |
| `MAX_DOWNLOAD_BYTES` | 524288000 (500MB) | 单文件上限 |
| `RATE_LIMIT_REQUESTS` | 30 | 窗口内请求上限 |
| `RATE_LIMIT_WINDOW_SEC` | 60 | 限流窗口秒数 |
| `MAX_CONCURRENT_DOWNLOADS` | 3 | 并发下载数 |
| `FREE_DAILY_PARSES` | `10`（`.env`；代码默认 999） | 每 IP 每日免费解析次数；Pro 无限 |
| `TEMP_FILE_TTL_SEC` | 3600 | 临时目录保留时间 |
| `FFMPEG_PATH` | 空（可另用 `ffmpeg.path` 文件） | ffmpeg 目录或可执行文件路径 |

AI 总结相关（`backend/.env`，参考 `.env.example`）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `LLM_API_KEY` / `DEEPSEEK_API_KEY` | 空 | 必填才可总结 |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI 兼容地址 |
| `LLM_MODEL` | `deepseek-chat` | 模型名 |
| `FREE_DAILY_SUMMARIES` | `10`（`.env`；代码默认 999） | 免费每日总结次数（匿名按 IP，登录按用户）；Pro 无限 |
| `SUMMARY_JOB_TTL_SEC` | `3600` | Job 保留时间 |
| `MAX_SUMMARY_CHARS` | `80000` | 送入 LLM 的字幕上限 |
| `MAX_CONCURRENT_SUMMARIES` | `2` | 并发总结任务数 |
| `BILI_COOKIE` / `SESSDATA` | 空 | 可选；部分 B 站人工 CC 需登录时使用 |
| `DATABASE_PATH` | `backend/data/app.db` | SQLite 路径 |
| `JWT_SECRET` | 开发默认（务必更换） | 会话签名密钥 |
| `PUBLIC_APP_URL` | `http://127.0.0.1:5173` | Checkout 成功/取消回跳 |
| `STRIPE_SECRET_KEY` | 空 | Stripe Secret（`sk_test_...`） |
| `STRIPE_WEBHOOK_SECRET` | 空 | Webhook 签名密钥（`whsec_...`） |
| `STRIPE_PRICE_ID` | 空 | 月度 Price ID（`price_...`） |

## AI 视频总结用法

1. 在 `backend/.env` 配置 `LLM_API_KEY`（或 `DEEPSEEK_API_KEY`）
2. 前端粘贴链接并解析；**解析成功后自动开始 AI 总结**（左右同屏展示）
3. 后端拉取字幕（yt-dlp → B 站 `dm/view` AI 字幕免登录回退等）→ **流式**生成 Markdown 笔记
4. 右侧四个 Tab：
   - 总结摘要（逐字打出）
   - 字幕文本
   - 思维导图（PNG 图片，可下载）
   - AI 问答（基于字幕）
5. 失败时可点「重试」或「重新总结」

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
- 下载解析配额仍为内存级 IP 限流；账号与订阅在 SQLite
- 大文件会占用服务器临时磁盘与带宽
- AI 总结依赖字幕：无字幕且无 AI 自动字幕时会报错（v1 不含 ASR 语音转写）
- 抖音等平台暂不支持总结
- YouTube 等在部分网络下可能超时
- Stripe 真实扣款需账号与网络；本地 webhook 依赖 Stripe CLI

## 目录结构

```
backend/app/                 # FastAPI 下载核心 + 总结 + 账号计费
  main.py                    # 下载路由；挂载 auth / billing / summary
  auth_router.py / db.py     # 注册登录、SQLite
  billing_router.py          # Stripe Checkout / webhook / portal
  summary_router.py          # 总结 / SSE / 问答 API
  subtitle_service.py        # 字幕拉取与解析
  llm_service.py             # DeepSeek 等 LLM（流式总结 / 问答）
  summary_jobs.py            # 内存异步 Job
frontend/
  .env.example               # VITE_SITE_URL（SEO/GEO 域名）
  src/auth/                  # 登录态与计费 API
  src/components/AuthModal.tsx / ProSection.tsx
  src/summary/               # AI 总结 UI（OCP）
docs/项目总结.md
docs/AI视频总结方案.md
docs/会员与Stripe支付.md
```

构建产物还会生成：`robots.txt`、`sitemap.xml`、`llms.txt`、`llms-full.txt`。

## 免责声明

仅供个人学习与合法备份。请遵守各平台 ToS 与版权法，勿用于未授权传播。
