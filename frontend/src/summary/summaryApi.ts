import type { SummaryJob, SummaryMeta } from './summaryTypes'

async function readError(res: Response): Promise<string> {
  try {
    const data = await res.json()
    if (typeof data?.detail === 'string') return data.detail
    return JSON.stringify(data)
  } catch {
    return res.statusText || '请求失败'
  }
}

export async function fetchSummaryMeta(): Promise<SummaryMeta> {
  const res = await fetch('/api/summary/meta')
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function startSummarize(
  url: string,
): Promise<{ job_id: string; remaining_summaries: number }> {
  const res = await fetch('/api/summarize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function fetchSummarizeStatus(jobId: string): Promise<SummaryJob> {
  const res = await fetch(`/api/summarize/${encodeURIComponent(jobId)}`)
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

/** Subscribe to SSE job updates. Returns an abort function. */
export function subscribeSummarizeEvents(
  jobId: string,
  handlers: {
    onUpdate: (job: SummaryJob) => void
    onError?: (message: string) => void
  },
): () => void {
  const es = new EventSource(`/api/summarize/${encodeURIComponent(jobId)}/events`)
  const onUpdate = (ev: MessageEvent) => {
    try {
      const data = JSON.parse(ev.data) as SummaryJob
      handlers.onUpdate(data)
    } catch {
      /* ignore */
    }
  }
  const onErrEvent = (ev: MessageEvent) => {
    try {
      const data = JSON.parse(ev.data) as { detail?: string }
      handlers.onError?.(data.detail || '流式更新失败')
    } catch {
      handlers.onError?.('流式更新失败')
    }
    es.close()
  }
  es.addEventListener('update', onUpdate as EventListener)
  es.addEventListener('end', (ev) => {
    onUpdate(ev as MessageEvent)
    es.close()
  })
  es.addEventListener('error', onErrEvent as EventListener)
  es.onerror = () => {
    // EventSource reconnects; if permanently failed browser keeps retrying — caller may abort
  }
  return () => es.close()
}

export async function askAboutVideo(
  jobId: string,
  question: string,
): Promise<string> {
  const res = await fetch(`/api/summarize/${encodeURIComponent(jobId)}/ask`, {
    method: 'POST',
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
