import { FileText, MoreHorizontal, Pencil, Trash2 } from 'lucide-react'
import { useState } from 'react'
import type { NotebookSummary } from '../../types'

interface NotebookCardProps {
  notebook: NotebookSummary
  onOpen: (id: string) => void
  onRename?: (id: string) => void
  onDelete?: (id: string) => void
}

export function NotebookCard({ notebook, onOpen, onRename, onDelete }: NotebookCardProps) {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onOpen(notebook.id)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onOpen(notebook.id)
        }
      }}
      className="group relative flex min-h-[152px] h-full cursor-pointer flex-col rounded-[10px] bg-white px-5 py-4 text-left shadow-[0_1px_0_rgba(43,52,55,0.02),0_10px_24px_rgba(43,52,55,0.04)] transition hover:-translate-y-0.5 hover:shadow-[0_10px_30px_rgba(43,52,55,0.08)] focus:outline-none focus:ring-2 focus:ring-primary/30"
    >
      <div className="mb-5 flex items-start justify-between gap-4">
        <div className="inline-flex items-center rounded-full bg-[rgba(112,68,193,0.12)] px-2.5 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-tertiary">
          {notebook.category}
        </div>
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation()
            setMenuOpen((current) => !current)
          }}
          className="rounded-md p-1 text-muted/75 transition hover:bg-surface-low hover:text-ink"
          aria-label={`Open menu for ${notebook.title}`}
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>

      <div className="space-y-2 text-left">
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

      {menuOpen && (
        <div className="absolute right-4 top-11 z-10 w-36 rounded-lg border border-black/8 bg-white py-1 text-[0.74rem] shadow-[0_12px_32px_rgba(43,52,55,0.16)]">
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation()
              setMenuOpen(false)
              onRename?.(notebook.id)
            }}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-ink transition hover:bg-surface-low"
          >
            <Pencil className="h-3.5 w-3.5" />
            Rename
          </button>
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation()
              setMenuOpen(false)
              onDelete?.(notebook.id)
            }}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-red-600 transition hover:bg-red-50"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </button>
        </div>
      )}
    </article>
  )
}
