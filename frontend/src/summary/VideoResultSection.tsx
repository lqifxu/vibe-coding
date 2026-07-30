import { useEffect, useRef, useState } from 'react'
import { ResultPanel } from '../components/ResultPanel'
import type { VideoFormat, VideoInfo } from '../types'
import { downloadSubtitles, type SubtitleDownloadFormat } from './summaryApi'
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

/** Composes download ResultPanel + AI summary (OCP extension). */
export function VideoResultSection({
  info,
  downloadingId,
  onDownload,
  onProClick,
}: Props) {
  const {
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

  const videoKey = info.webpage_url || info.id || info.title
  useResetOnVideoChange(videoKey, resetSummary)

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

  const showSummary = summarizing || !!summaryResult || !!summaryError

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

  return (
    <>
      <div className="mx-auto flex max-w-3xl flex-col items-end gap-2 px-4 pb-2 sm:px-6">
        <div className="flex flex-wrap justify-end gap-2">
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              disabled={subLoading}
              onClick={() => setSubMenuOpen((o) => !o)}
              className="rounded-full border border-line bg-white px-4 py-2 text-sm font-medium text-ink transition hover:bg-surface disabled:cursor-not-allowed disabled:opacity-60"
            >
              {subLoading ? '下载字幕中…' : '下载字幕'}
            </button>
            {subMenuOpen && (
              <div className="absolute right-0 z-20 mt-1 min-w-[7.5rem] overflow-hidden rounded-xl border border-line bg-white py-1 shadow-lg">
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
          <button
            type="button"
            disabled={summarizing}
            onClick={() => runSummarize(info.webpage_url)}
            className="rounded-full border border-brand/30 bg-brand/5 px-4 py-2 text-sm font-medium text-brand transition hover:bg-brand/10 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {summarizing ? '总结中…' : summaryResult ? '重新总结' : 'AI 总结'}
          </button>
        </div>
        {subError && (
          <p className="max-w-full text-right text-xs text-red-600">{subError}</p>
        )}
      </div>

      <ResultPanel info={info} downloadingId={downloadingId} onDownload={onDownload} />

      {showSummary && (
        <div className="mx-auto max-w-3xl px-4 pb-12 sm:px-6">
          <SummaryPanel
            loading={summarizing}
            stage={summaryStage}
            result={summaryResult}
            streamMarkdown={streamMarkdown}
            error={summaryError}
            qaMessages={qaMessages}
            qaLoading={qaLoading}
            onAsk={askQuestion}
            onRetry={() => runSummarize(info.webpage_url)}
            onProClick={onProClick}
          />
        </div>
      )}
    </>
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
