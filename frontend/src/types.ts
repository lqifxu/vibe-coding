export type VideoFormat = {
  format_id: string
  label: string
  ext: string
  height: number | null
  has_audio: boolean
  filesize: number | null
  filesize_text: string | null
  note: string | null
}

export type VideoInfo = {
  id: string | null
  title: string
  thumbnail: string | null
  duration: number | null
  extractor: string | null
  uploader: string | null
  webpage_url: string
  formats: VideoFormat[]
  remaining_parses?: number
}

export type HealthInfo = {
  ok: boolean
  yt_dlp: string
  ffmpeg: boolean
  free_daily_parses: number
}
