import {
  buildLlmsFullTxt,
  buildLlmsTxt,
  buildRobotsTxt,
  buildSitemapXml,
} from './src/seo/geoStatic.ts'
import { defineConfig, loadEnv, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

function normalizeSiteUrl(raw: string): string {
  return raw.replace(/\/+$/, '')
}

/** 按 VITE_SITE_URL 生成 robots / sitemap / llms.txt（开发中间件 + 构建产物） */
function seoStaticFiles(siteUrl: string): Plugin {
  const robots = buildRobotsTxt(siteUrl)
  const sitemap = buildSitemapXml(siteUrl)
  const llms = buildLlmsTxt(siteUrl)
  const llmsFull = buildLlmsFullTxt(siteUrl)

  return {
    name: 'seo-static-files',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const path = req.url?.split('?')[0]
        const map: Record<string, { type: string; body: string }> = {
          '/robots.txt': { type: 'text/plain; charset=utf-8', body: robots },
          '/sitemap.xml': { type: 'application/xml; charset=utf-8', body: sitemap },
          '/llms.txt': { type: 'text/plain; charset=utf-8', body: llms },
          '/llms-full.txt': { type: 'text/plain; charset=utf-8', body: llmsFull },
        }
        const hit = path ? map[path] : undefined
        if (hit) {
          res.setHeader('Content-Type', hit.type)
          res.end(hit.body)
          return
        }
        next()
      })
    },
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'robots.txt', source: robots })
      this.emitFile({ type: 'asset', fileName: 'sitemap.xml', source: sitemap })
      this.emitFile({ type: 'asset', fileName: 'llms.txt', source: llms })
      this.emitFile({ type: 'asset', fileName: 'llms-full.txt', source: llmsFull })
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const siteUrl = normalizeSiteUrl(env.VITE_SITE_URL || 'http://localhost:5173')

  return {
    plugins: [react(), tailwindcss(), seoStaticFiles(siteUrl)],
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8001',
          changeOrigin: true,
        },
      },
    },
  }
})
