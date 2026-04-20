import { Mic, Presentation, FileText, TableProperties } from 'lucide-react'
import type { StudioDocument } from '../../types'

export function StudioDocumentsPanel({ documents }: { documents: StudioDocument[] }) {
  return (
    <aside className="flex h-full flex-col">
      <div className="mb-6">
        <h2 className="text-[0.82rem] font-semibold uppercase tracking-[0.12em] text-ink">Studio</h2>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3">
        <button
          type="button"
          className="flex min-h-22 flex-col items-center justify-center gap-3 rounded-2xl bg-white/65 px-4 py-4 text-[0.78rem] font-medium text-ink shadow-[inset_0_0_0_1px_rgba(171,179,183,0.12)] transition hover:bg-white"
        >
          <Mic className="h-4 w-4 text-primary" />
          <span>Audio Overview</span>
        </button>
        <button
          type="button"
          className="flex min-h-22 flex-col items-center justify-center gap-3 rounded-2xl bg-white/65 px-4 py-4 text-[0.78rem] font-medium text-ink shadow-[inset_0_0_0_1px_rgba(171,179,183,0.12)] transition hover:bg-white"
        >
          <Presentation className="h-4 w-4 text-primary" />
          <span>Presentation</span>
        </button>
      </div>

      <div className="mb-4 text-[0.76rem] font-semibold uppercase tracking-[0.12em] text-ink">
        Saved Documents
      </div>

      <div className="space-y-3">
        {documents.map((document) => {
          const Icon = document.icon === 'description' ? FileText : TableProperties

          return (
            <article
              key={document.id}
              className="rounded-[18px] border border-black/5 bg-white px-4 py-4 shadow-[0_8px_22px_rgba(43,52,55,0.05)]"
            >
              <div className="flex items-start gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-surface-low text-primary">
                  <Icon className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <h3 className="text-[0.82rem] font-medium leading-5 text-ink">{document.title}</h3>
                  <p className="mt-1.5 text-[0.68rem] leading-5 text-muted">{document.excerpt}</p>
                  <p className="mt-2.5 text-[0.66rem] text-muted">{document.updatedAt}</p>
                </div>
              </div>
            </article>
          )
        })}
      </div>
    </aside>
  )
}
