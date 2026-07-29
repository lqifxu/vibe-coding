import { useEffect, useState } from 'react'
import { downloadVideo, fetchHealth, fetchInfo } from './api'
import { Footer } from './components/Footer'
import { Header } from './components/Header'
import { HeroParse } from './components/HeroParse'
import { PlatformGrid } from './components/PlatformGrid'
import { ProModal, ProSection } from './components/ProSection'
import { ResultPanel } from './components/ResultPanel'
import type { VideoFormat, VideoInfo } from './types'
import { extractUrlFromText, NO_URL_MESSAGE } from './urlExtract'

export default function App() {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const [info, setInfo] = useState<VideoInfo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [remaining, setRemaining] = useState<number | null>(null)
  const [proOpen, setProOpen] = useState(false)
  const [ffmpegOk, setFfmpegOk] = useState(true)

  useEffect(() => {
    fetchHealth()
      .then((h) => {
        setRemaining(h.free_daily_parses)
        setFfmpegOk(h.ffmpeg)
      })
      .catch(() => {})
  }, [])

  async function handleParse() {
    setError(null)
    setInfo(null)
    const trimmed = url.trim()
    if (!trimmed) {
      setError('请先粘贴视频链接或分享口令')
      return
    }
    const extracted = extractUrlFromText(trimmed)
    if (!extracted) {
      setError(NO_URL_MESSAGE)
      return
    }
    setLoading(true)
    try {
      const data = await fetchInfo(trimmed)
      setInfo(data)
      if (typeof data.remaining_parses === 'number') {
        setRemaining(data.remaining_parses)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '解析失败')
    } finally {
      setLoading(false)
    }
  }

  async function handleDownload(fmt: VideoFormat) {
    if (!info) return
    setError(null)
    setDownloadingId(fmt.format_id)
    try {
      const target = info.webpage_url || extractUrlFromText(url) || url.trim()
      await downloadVideo(target, fmt.format_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : '下载失败')
    } finally {
      setDownloadingId(null)
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <Header onProClick={() => setProOpen(true)} />
      <main className="flex-1">
        <HeroParse
          url={url}
          loading={loading}
          remaining={remaining}
          onUrlChange={setUrl}
          onSubmit={handleParse}
        />

        {!ffmpegOk && (
          <div className="mx-auto mb-4 max-w-3xl px-4 text-center text-xs text-amber-700 sm:px-6">
            当前服务器未检测到 ffmpeg：部分「需合并音轨」的高清格式可能失败，请优先选择带音轨的格式。
          </div>
        )}

        {error && (
          <div className="mx-auto mb-6 max-w-3xl px-4 sm:px-6">
            <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-left text-sm text-red-700">
              {error}
              {error.includes('Pro') && (
                <button
                  type="button"
                  className="ml-2 font-medium text-brand underline"
                  onClick={() => setProOpen(true)}
                >
                  查看 Pro
                </button>
              )}
            </div>
          </div>
        )}

        {info && (
          <ResultPanel
            info={info}
            downloadingId={downloadingId}
            onDownload={handleDownload}
          />
        )}

        <PlatformGrid />
        <ProSection onProClick={() => setProOpen(true)} />
      </main>
      <Footer />
      <ProModal open={proOpen} onClose={() => setProOpen(false)} />
    </div>
  )
}
