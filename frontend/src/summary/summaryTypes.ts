export type SummaryOutlinePoint = {
  label: string
  text: string
}

export type SummaryOutlineItem = {
  start: string
  start_sec: number
  title: string
  points: SummaryOutlinePoint[]
}

export type SummaryHighlight = {
  title: string
  text: string
}

export type SummaryChapter = {
  start: string
  start_sec: number
  title: string
  summary: string
}

export type SummaryCue = {
  start_sec: number
  start: string
  text: string
}

export type MindmapNode = {
  name: string
  children?: MindmapNode[]
}

export type SummaryResult = {
  title: string
  source?: string | null
  language?: string | null
  overview: string
  outline: SummaryOutlineItem[]
  highlights: SummaryHighlight[]
  conclusion: string
  cues?: SummaryCue[]
  transcript?: string
  mindmap?: MindmapNode | null
  stream_markdown?: string
  /** @deprecated legacy mirror of overview */
  summary?: string
  /** @deprecated legacy mirror of outline */
  chapters?: SummaryChapter[]
  webpage_url?: string | null
}

export type SummaryJob = {
  job_id: string
  status: 'queued' | 'running' | 'done' | 'failed'
  stage?: 'fetching_subtitles' | 'summarizing' | null
  result?: SummaryResult | null
  stream_markdown?: string
  error?: string | null
}

export type SummaryMeta = {
  llm_configured: boolean
  free_daily_summaries: number
  remaining_summaries?: number | null
  is_vip?: boolean
  provider_hint?: string
}

export type QaMessage = {
  role: 'user' | 'assistant'
  content: string
}
