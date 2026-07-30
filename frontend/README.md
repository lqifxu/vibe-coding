# 极速下 — 前端

Vite + React + TypeScript + Tailwind。本地开发默认 `:5173`，`/api` 代理到后端 `:8001`。

## 常用命令

```bash
npm install --registry=https://registry.npmmirror.com
npm run dev
npm run build
npm run preview
```

## SEO 域名

复制 `.env.example` 为 `.env`（若尚无），设置：

```bash
VITE_SITE_URL=http://localhost:5173
```

上线改为正式 `https` 域名后重新构建。`vite.config.ts` 会按该值生成 `robots.txt` / `sitemap.xml`；`index.html` 中的 `%VITE_SITE_URL%` 会在构建时替换。

相关模块：

| 路径 | 说明 |
|------|------|
| `index.html` | title / description / keywords / canonical / OG / JSON-LD |
| `src/seo/siteConfig.ts` | 站点名、描述、关键词常量 |
| `src/seo/geoStatic.ts` | robots / sitemap / llms.txt 生成逻辑 |
| `src/seo/geoCopy.ts` | GEO 定义、对比表、HowTo 步骤 |
| `src/seo/faqData.ts` | FAQ 文案（页面与 FAQPage 共用） |
| `src/components/GeoKnowledge.tsx` | 首页可抽取能力说明区 |
| `src/components/FeatureIntro.tsx` 等 | 其他可抓取内容区 |

本地可访问：`/llms.txt`、`/llms-full.txt`、`/robots.txt`。

根目录 [README.md](../README.md) 与 [docs/项目总结.md](../docs/项目总结.md) 有更完整说明。
