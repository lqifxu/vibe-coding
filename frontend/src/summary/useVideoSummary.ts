import { useCallback, useEffect, useRef, useState } from 'react'
import {
  askAboutVideoStream,
  fetchSummarizeStatus,
  fetchSummaryMeta,
  loadPersistedSummaryJobId,
  persistSummaryJobId,
  startSummarize,
  subscribeSummarizeEvents,
} from './summaryApi'
import type { QaMessage, SummaryJob, SummaryResult } from './summaryTypes'

export function useVideoSummary() {
  const [llmConfigured, setLlmConfigured] = useState(false)
  const [metaReady, setMetaReady] = useState(false)
  const [summarizing, setSummarizing] = useState(false)
  const [summaryStage, setSummaryStage] = useState<SummaryJob['stage'] | null>(null)
  const [summaryResult, setSummaryResult] = useState<SummaryResult | null>(null)
  const [summaryError, setSummaryError] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [streamMarkdown, setStreamMarkdown] = useState('')
  const [qaMessages, setQaMessages] = useState<QaMessage[]>([])
  const [qaLoading, setQaLoading] = useState(false)
  const [remainingSummaries, setRemainingSummaries] = useState<number | null | undefined>(
    undefined,
  )
  const [isVip, setIsVip] = useState(false)
  const unsubRef = useRef<(() => void) | null>(null)
  const askAbortRef = useRef<AbortController | null>(null)

  const clearSub = useCallback(() => {
    unsubRef.current?.()
    unsubRef.current = null
  }, [])

  const applyJob = useCallback(
    (job: SummaryJob) => {
      setSummaryStage(job.stage ?? null)
      if (job.stream_markdown) setStreamMarkdown(job.stream_markdown)
      if (job.result) setSummaryResult(job.result)
      if (job.status === 'done') {
        setSummarizing(false)
        setSummaryError(null)
        persistSummaryJobId(job.job_id || null)
        clearSub()
      } else if (job.status === 'failed') {
        setSummarizing(false)
        setSummaryError(job.error || '总结失败')
        clearSub()
      }
    },
    [clearSub],
  )

  useEffect(() => {
    fetchSummaryMeta()
      .then((m) => {
        setLlmConfigured(!!m.llm_configured)
        setIsVip(!!m.is_vip)
        if (m.is_vip) setRemainingSummaries(null)
        else if (typeof m.remaining_summaries === 'number') {
          setRemainingSummaries(m.remaining_summaries)
        }
      })
      .catch(() => setLlmConfigured(false))
      .finally(() => setMetaReady(true))
    return () => {
      unsubRef.current?.()
      askAbortRef.current?.abort()
    }
  }, [])

  // Restore in-flight / finished job after refresh (Douyin may outlive a tab).
  useEffect(() => {
    const saved = loadPersistedSummaryJobId()
    if (!saved) return
    let cancelled = false
    ;(async () => {
      try {
        const job = await fetchSummarizeStatus(saved)
        if (cancelled) return
        setJobId(saved)
        applyJob(job)
        if (job.status === 'queued' || job.status === 'running') {
          setSummarizing(true)
          clearSub()
          unsubRef.current = subscribeSummarizeEvents(saved, {
            onUpdate: applyJob,
            onError: (msg, meta) => {
              if (meta?.softTimeout) {
                setSummaryError(`${msg}（任务 ID：${meta.jobId || saved}）`)
                setSummarizing(true)
                return
              }
              setSummarizing(false)
              setSummaryError(msg)
              clearSub()
            },
          })
        }
      } catch {
        persistSummaryJobId(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [applyJob, clearSub])

  const resetSummary = useCallback(() => {
    clearSub()
    askAbortRef.current?.abort()
    persistSummaryJobId(null)
    setSummarizing(false)
    setSummaryStage(null)
    setSummaryResult(null)
    setSummaryError(null)
    setJobId(null)
    setStreamMarkdown('')
    setQaMessages([])
    setQaLoading(false)
  }, [clearSub])

  const runSummarize = useCallback(
    async (url: string) => {
      if (!llmConfigured) {
        setSummaryError(
          '服务器未配置 LLM_API_KEY（DeepSeek）。请在 backend/.env 中设置密钥后重启后端。',
        )
        setSummaryResult(null)
        return
      }
      clearSub()
      setSummaryError(null)
      setSummaryResult(null)
      setStreamMarkdown('')
      setQaMessages([])
      setSummarizing(true)
      setSummaryStage(null)
      try {
        const started = await startSummarize(url)
        setJobId(started.job_id)
        persistSummaryJobId(started.job_id)
        if (started.is_vip || started.remaining_summaries === null) {
          setIsVip(true)
          setRemainingSummaries(null)
        } else if (typeof started.remaining_summaries === 'number') {
          setIsVip(false)
          setRemainingSummaries(started.remaining_summaries)
        }
        unsubRef.current = subscribeSummarizeEvents(started.job_id, {
          onUpdate: applyJob,
          onError: (msg, meta) => {
            if (meta?.softTimeout) {
              setSummaryError(`${msg}（任务 ID：${meta.jobId || started.job_id}）`)
              return
            }
            setSummarizing(false)
            setSummaryError(msg)
            clearSub()
          },
        })
      } catch (e) {
        setSummarizing(false)
        setSummaryError(e instanceof Error ? e.message : '启动总结失败')
      }
    },
    [applyJob, clearSub, llmConfigured],
  )

  const askQuestion = useCallback(
    async (question: string) => {
      const q = question.trim()
      if (!q || !jobId || qaLoading) return
      setQaLoading(true)
      setQaMessages((prev) => [...prev, { role: 'user', content: q }, { role: 'assistant', content: '' }])
      askAbortRef.current?.abort()
      const ac = new AbortController()
      askAbortRef.current = ac
      try {
        await askAboutVideoStream(
          jobId,
          q,
          (delta) => {
            setQaMessages((prev) => {
              const next = [...prev]
              const last = next[next.length - 1]
              if (last?.role === 'assistant') {
                next[next.length - 1] = { ...last, content: last.content + delta }
              }
              return next
            })
          },
          ac.signal,
        )
      } catch (e) {
        const msg = e instanceof Error ? e.message : '回答失败'
        setQaMessages((prev) => {
          const next = [...prev]
          const last = next[next.length - 1]
          if (last?.role === 'assistant') {
            next[next.length - 1] = { ...last, content: last.content || msg }
          }
          return next
        })
      } finally {
        setQaLoading(false)
      }
    },
    [jobId, qaLoading],
  )

  return {
    llmConfigured,
    metaReady,
    summarizing,
    summaryStage,
    summaryResult,
    summaryError,
    streamMarkdown,
    jobId,
    qaMessages,
    qaLoading,
    remainingSummaries,
    isVip,
    runSummarize,
    resetSummary,
    askQuestion,
  }
}
