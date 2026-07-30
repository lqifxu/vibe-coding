import type { ReactNode } from 'react'

type Props = {
  left: ReactNode
  right: ReactNode
  className?: string
  /** Optional header above the split (e.g. demo title / stats). */
  header?: ReactNode
}

/** Shared two-column shell: stacked on mobile, side-by-side from lg. */
export function SplitResultShell({ left, right, className = '', header }: Props) {
  return (
    <section
      className={`mx-auto max-w-6xl animate-fade-up px-4 pb-12 sm:px-6 ${className}`.trim()}
    >
      {header}
      <div className="overflow-hidden rounded-2xl border border-line bg-white shadow-[0_8px_30px_-12px_rgba(15,23,42,0.12)]">
        <div className="grid grid-cols-1 lg:grid-cols-5">
          <div className="border-b border-line p-4 sm:p-5 lg:col-span-2 lg:border-b-0 lg:border-r">
            {left}
          </div>
          <div className="min-w-0 p-4 sm:p-5 lg:col-span-3">{right}</div>
        </div>
      </div>
    </section>
  )
}
