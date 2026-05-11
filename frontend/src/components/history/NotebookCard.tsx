import { FileText, MoreHorizontal } from 'lucide-react'
import type { NotebookSummary } from '../../types'

interface NotebookCardProps {
  notebook: NotebookSummary
  onOpen: (id: string) => void
  onDelete?: (id: string) => void
}

export function NotebookCard({ notebook, onOpen, onDelete }: NotebookCardProps) {
  return (
    <button
      type="button"
      onClick={() => onOpen(notebook.id)}
      className="group flex min-h-[152px] h-full flex-col rounded-[10px] bg-white px-5 py-4 text-left shadow-[0_1px_0_rgba(43,52,55,0.02),0_10px_24px_rgba(43,52,55,0.04)] transition hover:-translate-y-0.5 hover:shadow-[0_10px_30px_rgba(43,52,55,0.08)]"
    >
      <div className="mb-5 flex items-start justify-between gap-4">
        <div className="inline-flex items-center rounded-full bg-[rgba(112,68,193,0.12)] px-2.5 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-tertiary">
          {notebook.category}
        </div>
        <span
          role="button"
          tabIndex={0}
          onClick={(event) => {
            event.stopPropagation()
            onDelete?.(notebook.id)
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              event.stopPropagation()
              onDelete?.(notebook.id)
            }
          }}
          className="rounded-md p-1 text-muted/75 transition hover:bg-surface-low hover:text-ink"
          aria-label={`Delete ${notebook.title}`}
        >
          <MoreHorizontal className="h-4 w-4" />
        </span>
      </div>

      <div className="space-y-2">
        <h3 className="max-w-[24ch] text-[1.05rem] font-medium leading-[1.35] text-ink">
          {notebook.title}
        </h3>
      </div>

      <div className="mt-auto flex items-center justify-between gap-3 pt-6 text-[0.68rem] text-muted">
        <div className="flex items-center gap-1.5">
          <FileText className="h-3.5 w-3.5" />
          <span>{notebook.sourceCount} Sources</span>
        </div>
        <span>{notebook.updatedAt.replace('Updated ', '')}</span>
      </div>
    </button>
  )
}
