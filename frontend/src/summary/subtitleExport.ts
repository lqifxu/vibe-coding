import type { SummaryCue } from './summaryTypes'

export type SubtitleFormat = 'srt' | 'vtt' | 'txt'

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

function pad3(n: number): string {
  return String(n).padStart(3, '0')
}

/** SRT/VTT timestamp from seconds (HH:MM:SS,mmm or HH:MM:SS.mmm). */
export function formatSubtitleTs(sec: number, msSep: ',' | '.'): string {
  const totalMs = Math.max(0, Math.round(sec * 1000))
  const h = Math.floor(totalMs / 3600000)
  const m = Math.floor((totalMs % 3600000) / 60000)
  const s = Math.floor((totalMs % 60000) / 1000)
  const ms = totalMs % 1000
  return `${pad2(h)}:${pad2(m)}:${pad2(s)}${msSep}${pad3(ms)}`
}

function cueEndSec(cues: SummaryCue[], index: number): number {
  const start = cues[index].start_sec || 0
  if (index + 1 < cues.length) {
    const next = cues[index + 1].start_sec || start
    if (next > start) return next
  }
  return start + 2
}

export function cuesToSrt(cues: SummaryCue[]): string {
  const blocks: string[] = []
  cues.forEach((c, i) => {
    const start = formatSubtitleTs(c.start_sec || 0, ',')
    const end = formatSubtitleTs(cueEndSec(cues, i), ',')
    blocks.push(`${i + 1}\n${start} --> ${end}\n${c.text}\n`)
  })
  return blocks.join('\n')
}

export function cuesToVtt(cues: SummaryCue[]): string {
  const blocks = ['WEBVTT', '']
  cues.forEach((c, i) => {
    const start = formatSubtitleTs(c.start_sec || 0, '.')
    const end = formatSubtitleTs(cueEndSec(cues, i), '.')
    blocks.push(`${start} --> ${end}\n${c.text}\n`)
  })
  return blocks.join('\n')
}

export function cuesToTxt(cues: SummaryCue[], transcript?: string): string {
  if (transcript && transcript.trim()) return transcript
  return cues.map((c) => `[${c.start}] ${c.text}`).join('\n')
}

export function buildSubtitleContent(
  format: SubtitleFormat,
  cues: SummaryCue[] | undefined,
  transcript?: string,
): string | null {
  if (format === 'txt') {
    if (cues?.length) return cuesToTxt(cues, transcript)
    if (transcript?.trim()) return transcript
    return null
  }
  if (!cues?.length) return null
  return format === 'vtt' ? cuesToVtt(cues) : cuesToSrt(cues)
}

export function downloadTextFile(content: string, filename: string, mime: string): void {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` })
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(objectUrl)
}

export function downloadSubtitleFile(
  format: SubtitleFormat,
  cues: SummaryCue[] | undefined,
  transcript: string | undefined,
  title?: string,
): boolean {
  const content = buildSubtitleContent(format, cues, transcript)
  if (!content) return false
  const base = (title || 'subtitles').slice(0, 40).replace(/[\\/:*?"<>|]+/g, '_')
  const mime =
    format === 'vtt' ? 'text/vtt' : format === 'srt' ? 'application/x-subrip' : 'text/plain'
  downloadTextFile(content, `${base}.${format}`, mime)
  return true
}
