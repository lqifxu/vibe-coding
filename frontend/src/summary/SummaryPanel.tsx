import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { cleanMindmapLabel, downloadMindmapPng, mindmapToDataUrl } from './mindmapRender'
import {
  downloadSubtitleFile,
  type SubtitleFormat,
} from './subtitleExport'
import type {
  MindmapNode,
  QaMessage,
  SummaryCue,
  SummaryHighlight,
  SummaryJob,
  SummaryOutlineItem,
  SummaryResult,
} from './summaryTypes'

type Props = {
  loading: boolean
  stage: SummaryJob['stage'] | null
  result: SummaryResult | null
  streamMarkdown?: string
  error: string | null
  qaMessages: QaMessage[]
  qaLoading: boolean
  onAsk: (question: string) => void
  onRetry: () => void
  onProClick?: () => void
  /** Inside SplitResultShell — no outer card / top margin. */
  embedded?: boolean
  /** Marketing demo: soften QA input, keep copy optional. */
  demoMode?: boolean
}

type TabId = 'summary' | 'transcript' | 'mindmap' | 'qa'

const TABS: { id: TabId; label: string }[] = [
  { id: 'summary', label: '总结摘要' },
  { id: 'transcript', label: '字幕文本' },
  { id: 'mindmap', label: '思维导图' },
  { id: 'qa', label: 'AI 问答' },
]

function stageLabel(stage: SummaryJob['stage'] | null): string {
  if (stage === 'fetching_subtitles') return '正在提取字幕…'
  if (stage === 'summarizing') return '正在生成 AI 总结…'
  return '任务排队中…'
}

/** Clean title/body for summary UI: no markdown markers, no timeline stamps. */
function cleanText(text: string): string {
  return cleanMindmapLabel(text || '')
}

function normalizeResult(result: SummaryResult): {
  overview: string
  outline: SummaryOutlineItem[]
  highlights: SummaryHighlight[]
  conclusion: string
} {
  const overview = cleanText(result.overview || result.summary || '')
  const conclusion = cleanText(result.conclusion || '')

  let outline = result.outline || []
  if (!outline.length && result.chapters?.length) {
    outline = result.chapters.map((ch) => ({
      start: ch.start,
      start_sec: ch.start_sec,
      title: ch.title,
      points: ch.summary ? [{ label: '', text: ch.summary }] : [],
    }))
  }

  outline = outline.map((item) => ({
    ...item,
    title: cleanText(item.title) || '章节',
    points: (item.points || [])
      .map((p) => ({
        label: cleanText(p.label || ''),
        text: cleanText(p.text || ''),
      }))
      .filter((p) => p.text || p.label),
  }))

  let highlights: SummaryHighlight[] = []
  if (Array.isArray(result.highlights) && result.highlights.length) {
    highlights = result.highlights.map((h) =>
      typeof h === 'string'
        ? { title: '要点', text: cleanText(h) }
        : { title: cleanText(h.title || '') || '要点', text: cleanText(h.text || '') },
    )
  }

  return { overview, outline, highlights, conclusion }
}

/** Clean markdown for clipboard — no timestamps in outline titles. */
function toMarkdown(result: SummaryResult): string {
  const { overview, outline, highlights, conclusion } = normalizeResult(result)
  const lines: string[] = ['## 视频概述', overview || '（暂无）', '', '## 内容大纲']
  outline.forEach((item, i) => {
    lines.push(`${i + 1}. ${item.title}`)
    for (const p of item.points || []) {
      if (p.label) lines.push(`   - ${p.label}: ${p.text}`)
      else lines.push(`   - ${p.text}`)
    }
  })
  if (highlights.length) {
    lines.push('', '## 核心知识要点')
    highlights.forEach((h, i) => {
      lines.push(`${i + 1}. ${h.title}: ${h.text}`)
    })
  }
  if (conclusion) {
    lines.push('', '## 总结', conclusion)
  }
  lines.push('')
  return lines.join('\n')
}

function CopyButton({ result }: { result: SummaryResult }) {
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const t = window.setTimeout(() => setCopied(false), 2000)
    return () => window.clearTimeout(t)
  }, [copied])

  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(toMarkdown(result))
          setCopied(true)
        } catch {
          setCopied(false)
        }
      }}
      className="rounded-full border border-line px-3 py-1 text-xs font-medium text-ink hover:bg-surface"
    >
      {copied ? '已复制' : '复制 Markdown'}
    </button>
  )
}

function StreamingCursor() {
  return <span className="ml-0.5 inline-block h-4 w-1 animate-pulse bg-brand align-middle" />
}

function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <h3 className="mb-3 text-[1.05rem] font-bold tracking-tight text-ink sm:text-lg">{children}</h3>
  )
}

/** Document-style summary (matches clean reference UI — no raw MD, no timeline). */
function SummaryBody({
  result,
  streaming,
}: {
  result: SummaryResult
  streamMarkdown?: string
  streaming: boolean
}) {
  const { overview, outline, highlights, conclusion } = useMemo(
    () => normalizeResult(result),
    [result],
  )

  const hasAny = !!(overview || outline.length || highlights.length || conclusion)

  if (!hasAny && streaming) {
    return <p className="text-sm text-brand">正在生成总结…</p>
  }

  if (!hasAny) {
    return <p className="text-sm text-muted">暂无总结内容。</p>
  }

  return (
    <div className="space-y-8 text-left text-[15px] leading-7 text-ink/90">
      {overview && (
        <section>
          <SectionTitle>视频概述</SectionTitle>
          <p className="text-ink/85">
            {overview}
            {streaming && !outline.length && <StreamingCursor />}
          </p>
        </section>
      )}

      {outline.length > 0 && (
        <section>
          <SectionTitle>内容大纲</SectionTitle>
          <ol className="space-y-5">
            {outline.map((item, i) => (
              <li key={`${item.title}-${i}`} className="list-none">
                <div className="flex gap-2">
                  <span className="shrink-0 font-semibold text-brand">{i + 1}.</span>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-ink">{item.title}</p>
                    {(item.points || []).length > 0 && (
                      <ul className="mt-2 space-y-1.5">
                        {item.points.map((p, j) => (
                          <li key={j} className="flex gap-2 text-[14px] leading-6 text-ink/80">
                            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-brand/80" />
                            <span>
                              {p.label ? (
                                <>
                                  <span className="font-medium text-ink/90">{p.label}</span>
                                  <span className="text-ink/50">：</span>
                                  {p.text}
                                </>
                              ) : (
                                p.text
                              )}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ol>
          {streaming && !highlights.length && !conclusion && <StreamingCursor />}
        </section>
      )}

      {highlights.length > 0 && (
        <section>
          <SectionTitle>核心知识要点</SectionTitle>
          <ol className="space-y-3">
            {highlights.map((h, i) => (
              <li key={`${h.title}-${i}`} className="flex gap-2 list-none">
                <span className="shrink-0 font-semibold text-brand">{i + 1}.</span>
                <p className="text-ink/85">
                  <span className="font-semibold text-ink">{h.title}</span>
                  {h.text ? (
                    <>
                      <span className="text-ink/45">：</span>
                      {h.text}
                    </>
                  ) : null}
                </p>
              </li>
            ))}
          </ol>
          {streaming && !conclusion && <StreamingCursor />}
        </section>
      )}

      {conclusion && (
        <section>
          <SectionTitle>总结</SectionTitle>
          <p className="text-ink/85">
            {conclusion}
            {streaming && <StreamingCursor />}
          </p>
        </section>
      )}
    </div>
  )
}

function TranscriptExportBar({
  cues,
  transcript,
  title,
}: {
  cues?: SummaryCue[]
  transcript?: string
  title?: string
}) {
  const hasCues = !!(cues && cues.length > 0)
  const hasTxt = hasCues || !!(transcript && transcript.trim())
  if (!hasTxt) return null

  const formats: { id: SubtitleFormat; label: string; enabled: boolean }[] = [
    { id: 'srt', label: 'SRT', enabled: hasCues },
    { id: 'vtt', label: 'VTT', enabled: hasCues },
    { id: 'txt', label: 'TXT', enabled: hasTxt },
  ]

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-muted">下载字幕：</span>
      {formats.map((f) => (
        <button
          key={f.id}
          type="button"
          disabled={!f.enabled}
          onClick={() => downloadSubtitleFile(f.id, cues, transcript, title)}
          className="rounded-full border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface disabled:cursor-not-allowed disabled:opacity-40"
        >
          {f.label}
        </button>
      ))}
    </div>
  )
}

function TranscriptBody({
  cues,
  transcript,
  title,
}: {
  cues?: SummaryCue[]
  transcript?: string
  title?: string
}) {
  if (cues && cues.length > 0) {
    return (
      <div className="space-y-3">
        <TranscriptExportBar cues={cues} transcript={transcript} title={title} />
        <div className="max-h-[28rem] space-y-2 overflow-y-auto text-left text-sm">
          {cues.map((c, i) => (
            <div key={`${c.start}-${i}`} className="flex gap-3 border-b border-line/60 py-2">
              <span className="w-14 shrink-0 font-mono text-xs text-brand">{c.start}</span>
              <span className="text-ink/90">{c.text}</span>
            </div>
          ))}
        </div>
      </div>
    )
  }
  if (transcript) {
    return (
      <div className="space-y-3">
        <TranscriptExportBar transcript={transcript} title={title} />
        <pre className="max-h-[28rem] overflow-y-auto whitespace-pre-wrap rounded-xl bg-surface/60 p-3 text-left text-sm text-ink/90">
          {transcript}
        </pre>
      </div>
    )
  }
  return <p className="text-sm text-muted">暂无字幕文本。请先完成 AI 总结以提取字幕。</p>
}

function MindmapFullscreen({
  imgUrl,
  title,
  root,
  onClose,
}: {
  imgUrl: string
  title?: string
  root: MindmapNode
  onClose: () => void
}) {
  const [zoom, setZoom] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const dragging = useRef(false)
  const last = useRef({ x: 0, y: 0 })
  const viewportRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [onClose])

  const clampZoom = (z: number) => Math.min(4, Math.max(0.4, z))

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-slate-900/80 backdrop-blur-[2px]">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 bg-slate-950/70 px-3 py-2 text-white sm:px-4">
        <p className="truncate text-sm font-medium">{title || '思维导图'} · 全屏</p>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="rounded-full border border-white/20 px-3 py-1 text-xs hover:bg-white/10"
            onClick={() => setZoom((z) => clampZoom(z - 0.2))}
          >
            −
          </button>
          <button
            type="button"
            className="rounded-full border border-white/20 px-3 py-1 text-xs hover:bg-white/10"
            onClick={() => {
              setZoom(1)
              setOffset({ x: 0, y: 0 })
            }}
          >
            {Math.round(zoom * 100)}%
          </button>
          <button
            type="button"
            className="rounded-full border border-white/20 px-3 py-1 text-xs hover:bg-white/10"
            onClick={() => setZoom((z) => clampZoom(z + 0.2))}
          >
            +
          </button>
          <button
            type="button"
            className="rounded-full border border-white/20 px-3 py-1.5 text-xs hover:bg-white/10"
            onClick={() => downloadMindmapPng(root, title, 2)}
          >
            下载高清 PNG
          </button>
          <button
            type="button"
            className="rounded-full bg-white px-3 py-1.5 text-xs font-medium text-slate-900 hover:bg-slate-100"
            onClick={onClose}
          >
            关闭
          </button>
        </div>
      </div>
      <div
        ref={viewportRef}
        className="relative flex-1 cursor-grab overflow-hidden active:cursor-grabbing"
        onWheel={(e) => {
          e.preventDefault()
          const delta = e.deltaY > 0 ? -0.1 : 0.1
          setZoom((z) => clampZoom(z + delta))
        }}
        onPointerDown={(e) => {
          dragging.current = true
          last.current = { x: e.clientX, y: e.clientY }
          ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
        }}
        onPointerMove={(e) => {
          if (!dragging.current) return
          const dx = e.clientX - last.current.x
          const dy = e.clientY - last.current.y
          last.current = { x: e.clientX, y: e.clientY }
          setOffset((o) => ({ x: o.x + dx, y: o.y + dy }))
        }}
        onPointerUp={() => {
          dragging.current = false
        }}
        onPointerCancel={() => {
          dragging.current = false
        }}
      >
        <div
          className="absolute left-1/2 top-1/2 origin-center"
          style={{
            transform: `translate(calc(-50% + ${offset.x}px), calc(-50% + ${offset.y}px)) scale(${zoom})`,
          }}
        >
          <img
            src={imgUrl}
            alt="思维导图全屏"
            className="max-h-[85vh] max-w-[92vw] select-none rounded-lg bg-white shadow-2xl"
            draggable={false}
          />
        </div>
      </div>
      <p className="pb-3 text-center text-xs text-white/60">滚轮缩放 · 拖拽平移 · Esc 关闭</p>
    </div>
  )
}

function MindmapBody({ mindmap, title }: { mindmap?: MindmapNode | null; title?: string }) {
  const [imgUrl, setImgUrl] = useState<string | null>(null)
  const [hdUrl, setHdUrl] = useState<string | null>(null)
  const [fullscreen, setFullscreen] = useState(false)

  const root = useMemo<MindmapNode>(() => {
    if (mindmap?.name) return mindmap
    return { name: title || '视频总结', children: [] }
  }, [mindmap, title])

  useEffect(() => {
    if (!root.children?.length) {
      setImgUrl(null)
      setHdUrl(null)
      return
    }
    setImgUrl(mindmapToDataUrl(root, { scale: 1, fullText: true }))
    setHdUrl(mindmapToDataUrl(root, { scale: 2, fullText: true }))
  }, [root])

  if (!root.children?.length) {
    return <p className="text-sm text-muted">思维导图将在大纲生成后显示。</p>
  }

  return (
    <div className="space-y-3">
      {imgUrl ? (
        <button type="button" className="block w-full text-left" onClick={() => setFullscreen(true)}>
          <img
            src={imgUrl}
            alt="思维导图"
            className="w-full rounded-xl border border-line bg-[#f4f4f5] shadow-sm transition hover:border-brand/40"
          />
        </button>
      ) : (
        <p className="text-sm text-muted">正在生成导图图片…</p>
      )}
      {imgUrl && (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setFullscreen(true)}
            className="inline-flex rounded-full border border-brand/30 bg-brand/5 px-3 py-1.5 text-xs font-medium text-brand hover:bg-brand/10"
          >
            全屏查看
          </button>
          <button
            type="button"
            onClick={() => downloadMindmapPng(root, title, 2)}
            className="inline-flex rounded-full border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface"
          >
            下载高清图片
          </button>
        </div>
      )}
      {fullscreen && (hdUrl || imgUrl) && (
        <MindmapFullscreen
          imgUrl={hdUrl || imgUrl!}
          title={title}
          root={root}
          onClose={() => setFullscreen(false)}
        />
      )}
    </div>
  )
}

function QaBody({
  messages,
  loading,
  disabled,
  onAsk,
  demoMode,
}: {
  messages: QaMessage[]
  loading: boolean
  disabled: boolean
  onAsk: (q: string) => void
  demoMode?: boolean
}) {
  const [input, setInput] = useState('')
  const suggestions = ['这个视频的核心结论是什么？', '适合零基础吗？', '学习路线分哪几步？']

  return (
    <div className="space-y-3 text-left">
      <div className="max-h-72 space-y-3 overflow-y-auto rounded-xl border border-line bg-surface/40 p-3">
        {messages.length === 0 && (
          <p className="text-sm text-muted">
            {demoMode
              ? '演示对话如下。解析真实视频后可自由提问。'
              : '基于本视频字幕提问，例如学习路线、重点概念等。'}
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={`${m.role}-${i}`}
            className={[
              'rounded-xl px-3 py-2 text-sm whitespace-pre-wrap',
              m.role === 'user'
                ? 'ml-8 bg-brand/10 text-ink'
                : 'mr-8 border border-line bg-white text-ink/90',
            ].join(' ')}
          >
            {m.content || (loading && i === messages.length - 1 ? '思考中…' : '')}
            {loading && i === messages.length - 1 && m.role === 'assistant' && <StreamingCursor />}
          </div>
        ))}
      </div>
      {demoMode ? (
        <p className="text-xs text-muted">演示模式不支持提问，请在上方粘贴真实链接体验完整 AI 问答。</p>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((s) => (
              <button
                key={s}
                type="button"
                disabled={disabled || loading}
                onClick={() => onAsk(s)}
                className="rounded-full border border-line px-3 py-1 text-xs text-muted hover:border-brand/40 hover:text-brand disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              if (!input.trim()) return
              onAsk(input)
              setInput('')
            }}
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={disabled || loading}
              placeholder={disabled ? '请先完成总结后再提问' : '输入你的问题…'}
              className="flex-1 rounded-xl border border-line px-3 py-2 text-sm outline-none focus:border-brand"
            />
            <button
              type="submit"
              disabled={disabled || loading || !input.trim()}
              className="rounded-xl bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              发送
            </button>
          </form>
        </>
      )}
    </div>
  )
}

export function SummaryPanel({
  loading,
  stage,
  result,
  streamMarkdown,
  error,
  qaMessages,
  qaLoading,
  onAsk,
  onRetry,
  onProClick,
  embedded = false,
  demoMode = false,
}: Props) {
  const [tab, setTab] = useState<TabId>('summary')
  const hasPartial =
    !!result &&
    (!!result.overview ||
      (result.outline && result.outline.length > 0) ||
      !!result.cues?.length ||
      !!streamMarkdown)

  const shellClass = embedded
    ? 'flex min-h-0 flex-1 flex-col overflow-hidden'
    : 'mt-4 overflow-hidden rounded-2xl border border-line bg-white shadow-[0_8px_30px_-12px_rgba(15,23,42,0.12)]'

  return (
    <div className={shellClass}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-1 pt-1 sm:px-2">
        <div className="flex min-w-0 flex-1 gap-1 overflow-x-auto pb-px">
          {TABS.map((t) => {
            const active = tab === t.id
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={[
                  'shrink-0 whitespace-nowrap rounded-t-lg px-2.5 py-2 text-sm transition sm:px-3 sm:py-2.5',
                  active
                    ? 'border-b-2 border-brand font-medium text-brand'
                    : 'text-muted hover:text-ink',
                ].join(' ')}
              >
                {t.label}
              </button>
            )
          })}
        </div>
        {result && result.overview && (
          <div className="pb-2 pr-1">
            <CopyButton result={result} />
          </div>
        )}
      </div>

      <div className={embedded ? 'max-h-[32rem] overflow-y-auto py-3 lg:max-h-[36rem]' : 'px-4 py-4 sm:px-5'}>
        {loading && !hasPartial && (
          <div className="rounded-xl border border-dashed border-brand/30 bg-brand/5 px-4 py-6 text-center text-sm text-brand">
            {stageLabel(stage)}
          </div>
        )}

        {!loading && error && !hasPartial && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-left text-sm text-red-700">
            {error}
            {error.includes('Pro') && onProClick && (
              <button
                type="button"
                className="ml-2 font-medium text-brand underline"
                onClick={onProClick}
              >
                查看 Pro
              </button>
            )}
            {!demoMode && (
              <button
                type="button"
                onClick={onRetry}
                className="ml-2 font-medium text-ink underline"
              >
                重试
              </button>
            )}
          </div>
        )}

        {(hasPartial || (!loading && result)) && tab === 'summary' && result && (
          <SummaryBody
            result={result}
            streamMarkdown={streamMarkdown}
            streaming={loading}
          />
        )}

        {tab === 'transcript' && (
          <TranscriptBody
            cues={result?.cues}
            transcript={result?.transcript}
            title={result?.title}
          />
        )}

        {tab === 'mindmap' && (
          <MindmapBody mindmap={result?.mindmap} title={result?.title} />
        )}

        {tab === 'qa' && (
          <QaBody
            messages={qaMessages}
            loading={qaLoading}
            disabled={demoMode || !result?.transcript}
            onAsk={onAsk}
            demoMode={demoMode}
          />
        )}
      </div>
    </div>
  )
}
