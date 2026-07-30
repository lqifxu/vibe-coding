import { useEffect, useRef, useState } from 'react'
import { ResultPanel } from '../components/ResultPanel'
import type { VideoFormat, VideoInfo } from '../types'
import { downloadSubtitles, type SubtitleDownloadFormat } from './summaryApi'
import { SplitResultShell } from './SplitResultShell'
import { SummaryPanel } from './SummaryPanel'
import { useVideoSummary } from './useVideoSummary'

type Props = {
  info: VideoInfo
  downloadingId: string | null
  onDownload: (fmt: VideoFormat) => void
  onProClick?: () => void
}

const SUB_FORMATS: { id: SubtitleDownloadFormat; label: string }[] = [
  { id: 'srt', label: 'SRT' },
  { id: 'vtt', label: 'VTT' },
  { id: 'txt', label: 'TXT' },
]

/** Composes download ResultPanel + AI summary side-by-side (OCP extension). */
export function VideoResultSection({
  info,
  downloadingId,
  onDownload,
  onProClick,
}: Props) {
  const {
    llmConfigured,
    metaReady,
    summarizing,
    summaryStage,
    summaryResult,
    summaryError,
    streamMarkdown,
    qaMessages,
    qaLoading,
    runSummarize,
    resetSummary,
    askQuestion,
  } = useVideoSummary()

  const [subLoading, setSubLoading] = useState(false)
  const [subError, setSubError] = useState<string | null>(null)
  const [subMenuOpen, setSubMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement | null>(null)
  const lastAutoKeyRef = useRef<string | null>(null)

  const videoKey = info.webpage_url || info.id || info.title
  useResetOnVideoChange(videoKey, () => {
    lastAutoKeyRef.current = null
    resetSummary()
  })

  // Auto-summarize after parse when LLM is configured (wait for meta).
  useEffect(() => {
    if (!metaReady || !llmConfigured || !videoKey) return
    if (lastAutoKeyRef.current === videoKey) return
    lastAutoKeyRef.current = videoKey
    runSummarize(info.webpage_url)
  }, [metaReady, llmConfigured, videoKey, info.webpage_url, runSummarize])

  useEffect(() => {
    if (!subMenuOpen) return
    const onDoc = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setSubMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [subMenuOpen])

  const handleSubtitleDownload = async (format: SubtitleDownloadFormat) => {
    setSubMenuOpen(false)
    setSubError(null)
    setSubLoading(true)
    try {
      await downloadSubtitles(info.webpage_url, format)
    } catch (e) {
      setSubError(e instanceof Error ? e.message : '字幕下载失败')
    } finally {
      setSubLoading(false)
    }
  }

  const waitingMeta = !metaReady
  const llmMissing = metaReady && !llmConfigured
  const displayError =
    summaryError ||
    (llmMissing
      ? '服务器未配置 LLM_API_KEY（DeepSeek）。请在 backend/.env 中设置密钥后重启后端。'
      : null)

  const leftActions = (
    <>
      <div className="relative" ref={menuRef}>
        <button
          type="button"
          disabled={subLoading}
          onClick={() => setSubMenuOpen((o) => !o)}
          className="rounded-full border border-line bg-white px-3 py-1.5 text-sm font-medium text-ink transition hover:bg-surface disabled:cursor-not-allowed disabled:opacity-60"
        >
          {subLoading ? '下载字幕中…' : '下载字幕'}
        </button>
        {subMenuOpen && (
          <div className="absolute left-0 z-20 mt-1 min-w-[7.5rem] overflow-hidden rounded-xl border border-line bg-white py-1 shadow-lg">
            {SUB_FORMATS.map((f) => (
              <button
                key={f.id}
                type="button"
                className="block w-full px-4 py-2 text-left text-sm text-ink hover:bg-surface"
                onClick={() => handleSubtitleDownload(f.id)}
              >
                {f.label}
              </button>
            ))}
          </div>
        )}
      </div>
      {(summaryResult || summarizing) && (
        <button
          type="button"
          disabled={summarizing || !llmConfigured}
          onClick={() => runSummarize(info.webpage_url)}
          className="rounded-full border border-brand/30 bg-brand/5 px-3 py-1.5 text-sm font-medium text-brand transition hover:bg-brand/10 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {summarizing ? '总结中…' : '重新总结'}
        </button>
      )}
      {subError && <p className="w-full text-xs text-red-600">{subError}</p>}
    </>
  )

  return (
    <SplitResultShell
      left={
        <ResultPanel
          info={info}
          downloadingId={downloadingId}
          onDownload={onDownload}
          actions={leftActions}
          embedded
        />
      }
      right={
        <div className="flex h-full min-h-[16rem] flex-col">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="font-display text-sm font-semibold text-ink sm:text-base">AI 视频总结</h3>
            {waitingMeta && <span className="text-xs text-muted">检查 AI 服务…</span>}
          </div>
          <SummaryPanel
            loading={summarizing || waitingMeta}
            stage={waitingMeta ? null : summaryStage}
            result={summaryResult}
            streamMarkdown={streamMarkdown}
            error={displayError}
            qaMessages={qaMessages}
            qaLoading={qaLoading}
            onAsk={askQuestion}
            onRetry={() => runSummarize(info.webpage_url)}
            onProClick={onProClick}
            embedded
          />
        </div>
      }
    />
  )
}

function useResetOnVideoChange(key: string | null | undefined, reset: () => void) {
  const prev = useRef(key)
  useEffect(() => {
    if (prev.current !== key) {
      prev.current = key
      reset()
    }
  }, [key, reset])
}
