# 极速下 — 万能视频下载网站

粘贴视频链接或分享口令 → 解析清晰度 → 下载到本地（手机 / 电脑均可）。  
下载引擎基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp)；抖音走独立无 Cookie 分享页解析。无数据库。

更完整的设计取舍与验收记录见：[docs/项目总结.md](docs/项目总结.md)

## 功能（MVP）

- 解析多平台视频信息与清晰度列表，下载到浏览器本地
- 仿 [鱼皮 AI 绘图](https://ai.codefather.cn/painting) 风格的转化型落地页
- Pro / 批量 / 字幕翻译 / AI 总结入口占位（未接真实支付）
- IP 限流 + 每日免费解析次数（内存，重启清空）

## 环境要求

- **Python 3.10+**（推荐 3.12；可用 `backend/.venv`）
- **Node.js 18+**
- **ffmpeg**（强烈建议；高清音视频合并需要）

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
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：<http://127.0.0.1:8000/api/health>

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
开发服务器已将 `/api` 代理到后端 `8000` 端口。

## 抖音取链说明

| 可用 | 示例 |
|------|------|
| 分享口令（含链接） | 文案中带 `https://v.douyin.com/...` |
| 标准视频页 | `https://www.douyin.com/video/数字ID` |
| 网页弹窗地址 | `https://www.douyin.com/jingxuan?modal_id=数字ID` |

**不要**复制无视频 ID 的推荐页，例如 `https://www.douyin.com/?recommend=1`。  
抖音解析**无需登录、无需填写 Cookie**。

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | yt-dlp / ffmpeg 状态 |
| POST | `/api/info` | Body `{ "url" }` → 标题、封面、清晰度 |
| POST | `/api/download` | Body `{ "url", "format_id" }` → 文件流 |

## 配置（环境变量）

| 变量 | 默认 | 说明 |
|------|------|------|
| `TEMP_DIR` | `backend/temp` | 临时下载目录 |
| `MAX_DOWNLOAD_BYTES` | 524288000 (500MB) | 单文件上限 |
| `RATE_LIMIT_REQUESTS` | 30 | 窗口内请求上限 |
| `RATE_LIMIT_WINDOW_SEC` | 60 | 限流窗口秒数 |
| `MAX_CONCURRENT_DOWNLOADS` | 3 | 并发下载数 |
| `FREE_DAILY_PARSES` | 20（代码默认；本地可改配置调高） | 每 IP 每日免费解析次数 |
| `TEMP_FILE_TTL_SEC` | 3600 | 临时目录保留时间 |
| `FFMPEG_PATH` | 空（可另用 `ffmpeg.path` 文件） | ffmpeg 目录或可执行文件路径 |

## 已知限制

- 部分平台风控 / 网络环境可能导致失败，失败时返回友好错误
- 未配置 ffmpeg 时，「需合并音轨」的高清格式可能失败
- 无数据库，配额为内存级粗限流，适合演示与小流量
- 大文件会占用服务器临时磁盘与带宽

## 目录结构

```
backend/app/          # FastAPI + yt-dlp + 抖音专项
frontend/src/         # Vite React 落地页
docs/项目总结.md       # 设计沉淀与验收总结
```

## 免责声明

仅供个人学习与合法备份。请遵守各平台 ToS 与版权法，勿用于未授权传播。