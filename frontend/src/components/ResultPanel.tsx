import type { VideoFormat, VideoInfo } from '../types'

function formatDuration(sec: number | null): string {
  if (!sec && sec !== 0) return ''
  const s = Math.floor(sec)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const r = s % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`
  return `${m}:${String(r).padStart(2, '0')}`
}

type Props = {
  info: VideoInfo
  downloadingId: string | null
  onDownload: (fmt: VideoFormat) => void
}

export function ResultPanel({ info, downloadingId, onDownload }: Props) {
  return (
    <section className="mx-auto max-w-3xl animate-fade-up px-4 pb-12 sm:px-6">
      <div className="overflow-hidden rounded-2xl border border-line bg-white shadow-[0_8px_30px_-12px_rgba(15,23,42,0.12)]">
        <div className="flex flex-col gap-4 p-4 sm:flex-row sm:p-5">
          <div className="aspect-video w-full shrink-0 overflow-hidden rounded-xl bg-surface sm:w-48">
            {info.thumbnail ? (
              <img
                src={info.thumbnail}
                alt=""
                className="h-full w-full object-cover"
                referrerPolicy="no-referrer"
              />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted">无封面</div>
            )}
          </div>
          <div className="min-w-0 flex-1 text-left">
            <h2 className="line-clamp-2 font-display text-lg font-semibold text-ink sm:text-xl">
              {info.title}
            </h2>
            <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-sm text-muted">
              {info.extractor && <span>{info.extractor}</span>}
              {info.uploader && <span>{info.uploader}</span>}
              {info.duration != null && <span>{formatDuration(info.duration)}</span>}
            </p>
          </div>
        </div>

        <div className="border-t border-line px-4 py-3 sm:px-5">
          <p className="mb-2 text-left text-xs font-medium uppercase tracking-wide text-muted">
            选择清晰度下载
          </p>
          <ul className="space-y-2">
            {info.formats.map((fmt) => {
              const busy = downloadingId === fmt.format_id
              return (
                <li
                  key={fmt.format_id + fmt.label}
                  className="flex flex-col gap-2 rounded-xl border border-line/80 bg-surface/50 px-3 py-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="text-left">
                    <div className="font-medium text-ink">
                      {fmt.label}
                      <span className="ml-2 text-sm font-normal text-muted">.{fmt.ext}</span>
                    </div>
                    <div className="mt-0.5 text-xs text-muted">
                      {[fmt.filesize_text, fmt.note].filter(Boolean).join(' · ') || '大小未知'}
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={!!downloadingId}
                    onClick={() => onDownload(fmt)}
                    className="rounded-full bg-brand px-5 py-2 text-sm font-medium text-white transition hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {busy ? '下载中…' : '下载'}
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      </div>
    </section>
  )
}
