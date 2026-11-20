import type { SummaryJob, SummaryMeta } from './summaryTypes'

const JOB_STORAGE_KEY = 'jisuxia_summary_job_id'
/** Max time to poll after SSE soft-timeout / disconnect while job still running. */
export const SUMMARY_POLL_MAX_MS = 5 * 60 * 1000
export const SUMMARY_POLL_INTERVAL_MS = 2000

async function readError(res: Response): Promise<string> {
  try {
    const data = await res.json()
    if (typeof data?.detail === 'string') return data.detail
    return JSON.stringify(data)
  } catch {
    return res.statusText || '请求失败'
  }
}

export function persistSummaryJobId(jobId: string | null): void {
  try {
    if (jobId) sessionStorage.setItem(JOB_STORAGE_KEY, jobId)
    else sessionStorage.removeItem(JOB_STORAGE_KEY)
  } catch {
    /* ignore */
  }
}

export function loadPersistedSummaryJobId(): string | null {
  try {
    return sessionStorage.getItem(JOB_STORAGE_KEY)
  } catch {
    return null
  }
}

export async function fetchSummaryMeta(): Promise<SummaryMeta> {
  const res = await fetch('/api/summary/meta', { credentials: 'include' })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function startSummarize(
  url: string,
): Promise<{ job_id: string; remaining_summaries: number | null; is_vip?: boolean }> {
  const res = await fetch('/api/summarize', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function fetchSummarizeStatus(jobId: string): Promise<SummaryJob> {
  const res = await fetch(`/api/summarize/${encodeURIComponent(jobId)}`, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

type SubscribeHandlers = {
  onUpdate: (job: SummaryJob) => void
  onDelta?: (delta: string) => void
  onError?: (message: string, meta?: { softTimeout?: boolean; jobId?: string }) => void
}

/**
 * Prefer SSE; if the stream ends with soft_timeout or drops while the job is
 * still running/queued, fall back to GET polling for up to 5 minutes.
 */
export function subscribeSummarizeEvents(
  jobId: string,
  handlers: SubscribeHandlers,
): () => void {
  let closed = false
  let es: EventSource | null = null
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  const pollDeadline = Date.now() + SUMMARY_POLL_MAX_MS

  const stop = () => {
    closed = true
    es?.close()
    es = null
    if (pollTimer != null) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  const schedulePoll = () => {
    if (closed) return
    if (Date.now() > pollDeadline) {
      handlers.onError?.(
        '任务仍在后台处理，可刷新页面或稍后凭任务恢复查询',
        { softTimeout: true, jobId },
      )
      return
    }
    pollTimer = setTimeout(async () => {
      if (closed) return
      try {
        const job = await fetchSummarizeStatus(jobId)
        handlers.onUpdate(job)
        if (job.status === 'done' || job.status === 'failed') {
          stop()
          return
        }
        // still queued/running — keep polling
        schedulePoll()
      } catch (e) {
        const msg = e instanceof Error ? e.message : '轮询失败'
        handlers.onError?.(msg, { jobId })
      }
    }, SUMMARY_POLL_INTERVAL_MS)
  }

  const startPollingFallback = () => {
    es?.close()
    es = null
    schedulePoll()
  }

  es = new EventSource(`/api/summarize/${encodeURIComponent(jobId)}/events`)

  const onUpdate = (ev: MessageEvent) => {
    try {
      const data = JSON.parse(ev.data) as SummaryJob
      handlers.onUpdate(data)
      if (data.status === 'done' || data.status === 'failed') {
        stop()
      }
    } catch {
      /* ignore */
    }
  }

  const onErrEvent = (ev: MessageEvent) => {
    // Named SSE `event: error` from server has JSON data; browser transport
    // errors often have empty data — treat those as poll fallback, not UI failure.
    if (ev.data) {
      let soft = false
      let detail = '流式更新中断'
      try {
        const data = JSON.parse(ev.data) as {
          detail?: string
          soft_timeout?: boolean
          job_id?: string
        }
        detail = data.detail || detail
        soft = !!data.soft_timeout || /后台处理|继续|超时/.test(detail)
      } catch {
        startPollingFallback()
        return
      }
      es?.close()
      es = null
      if (soft) {
        startPollingFallback()
        return
      }
      handlers.onError?.(detail, { jobId })
      stop()
      return
    }
    if (es && es.readyState === EventSource.CLOSED) {
      startPollingFallback()
    }
  }

  es.addEventListener('delta', ((ev: MessageEvent) => {
    try {
      const data = JSON.parse(ev.data) as { delta?: string }
      if (data.delta) handlers.onDelta?.(data.delta)
    } catch {
      /* ignore */
    }
  }) as EventListener)
  es.addEventListener('update', onUpdate as EventListener)
  es.addEventListener('end', (ev) => {
    onUpdate(ev as MessageEvent)
    stop()
  })
  es.addEventListener('error', onErrEvent as EventListener)
  es.onerror = () => {
    // Only fall back when the browser permanently closed the stream.
    // Transient onerror fires during normal EventSource reconnects.
    if (closed || !es) return
    if (es.readyState === EventSource.CLOSED) {
      startPollingFallback()
    }
  }

  return stop
}

export async function askAboutVideo(
  jobId: string,
  question: string,
): Promise<string> {
  const res = await fetch(`/api/summarize/${encodeURIComponent(jobId)}/ask`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  if (!res.ok) throw new Error(await readError(res))
  const data = (await res.json()) as { answer: string }
  return data.answer
}

export type SubtitleDownloadFormat = 'srt' | 'vtt' | 'txt'

/** Download subtitle file via dedicated API (no LLM / no summary quota). */
export async function downloadSubtitles(
  url: string,
  format: SubtitleDownloadFormat = 'srt',
): Promise<void> {
  const res = await fetch('/api/subtitles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, format }),
  })
  if (!res.ok) throw new Error(await readError(res))

  const blob = await res.blob()
  const disposition = res.headers.get('Content-Disposition') || ''
  let filename = `subtitles.${format}`
  const m = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(disposition)
  if (m) {
    filename = decodeURIComponent(m[1] || m[2])
  }

  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(objectUrl)
}

export async function askAboutVideoStream(
  jobId: string,
  question: string,
  onDelta: (delta: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`/api/summarize/${encodeURIComponent(jobId)}/ask/stream`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
    signal,
  })
  if (!res.ok) throw new Error(await readError(res))
  if (!res.body) throw new Error('浏览器不支持流式响应')
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const parts = buf.split('\n\n')
    buf = parts.pop() || ''
    for (const part of parts) {
      const line = part
        .split('\n')
        .map((l) => l.trim())
        .find((l) => l.startsWith('data:'))
      if (!line) continue
      const raw = line.slice(5).trim()
      try {
        const data = JSON.parse(raw) as { delta?: string; error?: string; done?: boolean }
        if (data.error) throw new Error(data.error)
        if (data.delta) onDelta(data.delta)
      } catch (e) {
        if (e instanceof Error && e.message && !e.message.includes('JSON')) throw e
      }
    }
  }
}
