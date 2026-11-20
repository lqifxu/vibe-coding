import { useEffect, useState } from 'react'
import { downloadVideo, fetchHealth, fetchInfo } from './api'
import { useAuth } from './auth/useAuth'
import { AuthModal } from './components/AuthModal'
import { FaqSection } from './components/FaqSection'
import { FeatureIntro } from './components/FeatureIntro'
import { Footer } from './components/Footer'
import { GeoKnowledge } from './components/GeoKnowledge'
import { Header } from './components/Header'
import { HeroParse } from './components/HeroParse'
import { HowItWorks } from './components/HowItWorks'
import { PlatformGrid } from './components/PlatformGrid'
import { ProModal, ProSection } from './components/ProSection'
import { SeoJsonLd } from './seo/SeoJsonLd'
import { VideoResultSection } from './summary/VideoResultSection'
import type { VideoFormat, VideoInfo } from './types'
import { extractUrlFromText, NO_URL_MESSAGE } from './urlExtract'

export default function App() {
  const auth = useAuth()
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const [info, setInfo] = useState<VideoInfo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [remaining, setRemaining] = useState<number | null | undefined>(undefined)
  const [proOpen, setProOpen] = useState(false)
  const [authOpen, setAuthOpen] = useState(false)
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [ffmpegOk, setFfmpegOk] = useState(true)

  useEffect(() => {
    fetchHealth()
      .then((h) => {
        setFfmpegOk(h.ffmpeg)
        if (h.is_vip || h.remaining_parses === null) setRemaining(null)
        else if (typeof h.remaining_parses === 'number') setRemaining(h.remaining_parses)
        else setRemaining(h.free_daily_parses)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (auth.user.is_vip) setRemaining(null)
  }, [auth.user.is_vip])

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
      if (data.is_vip || data.remaining_parses === null) {
        setRemaining(null)
      } else if (typeof data.remaining_parses === 'number') {
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

  function openPro() {
    setProOpen(true)
  }

  function openLogin() {
    setAuthMode('login')
    setAuthOpen(true)
  }

  return (
    <div className="flex min-h-screen flex-col">
      <SeoJsonLd />
      <Header
        user={auth.user}
        onProClick={openPro}
        onLoginClick={openLogin}
        onLogout={() => void auth.logout()}
        onPortal={() => void auth.openPortal().catch((e) => setError(e instanceof Error ? e.message : '打开失败'))}
      />
      <main className="flex-1">
        {auth.billingNotice && (
          <div className="mx-auto mt-4 max-w-3xl px-4 sm:px-6">
            <div className="flex items-start justify-between gap-3 rounded-2xl border border-brand/20 bg-brand/5 px-4 py-3 text-sm text-ink">
              <span>{auth.billingNotice}</span>
              <button
                type="button"
                className="text-muted hover:text-ink"
                onClick={auth.clearBillingNotice}
              >
                关闭
              </button>
            </div>
          </div>
        )}

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
                  onClick={openPro}
                >
                  查看 Pro
                </button>
              )}
              {(error.includes('B站') || error.includes('Bilibili') || error.includes('bilibili')) && (
                <p className="mt-2 text-xs leading-relaxed text-red-600/90">
                  请确认是投稿视频链接（含 BV 号）。番剧 EP 暂不支持；若仍失败可稍后再试或改用抖音 / YouTube。
                </p>
              )}
            </div>
          </div>
        )}

        {info && (
          <VideoResultSection
            info={info}
            downloadingId={downloadingId}
            onDownload={handleDownload}
            onProClick={openPro}
            isVip={auth.user.is_vip}
            remainingSummaries={auth.user.authenticated ? auth.user.remaining_summaries ?? null : null}
          />
        )}

        <PlatformGrid />
        <FeatureIntro />
        <HowItWorks />
        <GeoKnowledge />
        <FaqSection />
        <ProSection onProClick={openPro} />
      </main>
      <Footer />
      <ProModal
        open={proOpen}
        onClose={() => setProOpen(false)}
        user={auth.user}
        onNeedLogin={openLogin}
        onCheckout={auth.startCheckout}
        onPortal={auth.openPortal}
      />
      <AuthModal
        open={authOpen}
        mode={authMode}
        onModeChange={setAuthMode}
        onClose={() => setAuthOpen(false)}
        onSubmit={async (email, password, mode) => {
          if (mode === 'login') await auth.login(email, password)
          else await auth.register(email, password)
        }}
      />
    </div>
  )
}
