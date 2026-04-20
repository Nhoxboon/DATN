import { Bookmark, Copy, Sparkles, ThumbsDown, ThumbsUp } from 'lucide-react'
import type { NotebookDetail } from '../../types'
import { useTypewriter } from '../../hooks/useTypewriter'

export function SynthesisCard({ notebook }: { notebook: NotebookDetail }) {
  const typedBody = useTypewriter(notebook.synthesisBody, 8)

  return (
    <section className="px-6 py-6 sm:px-7">
      <div className="mb-5 flex items-center gap-2">
        <div className="inline-flex items-center gap-1.5 rounded-md bg-[rgba(0,91,192,0.08)] px-2.5 py-1.5 text-[0.68rem] font-semibold uppercase tracking-[0.15em] text-primary">
          <Sparkles className="h-3.5 w-3.5" />
          {notebook.synthesisTitle}
        </div>
      </div>

      <div className="space-y-5 text-[1rem] leading-8 text-ink">
        <p>{typedBody}</p>
        <ul className="space-y-3 text-[0.96rem] leading-7 text-ink">
          {notebook.synthesisBullets.map((point) => (
            <li key={point} className="flex gap-3">
              <span className="mt-[0.55rem] h-1.5 w-1.5 rounded-full bg-ink" />
              <span>{point}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-7 flex items-center justify-between gap-4">
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-xl border border-outline/50 px-3.5 py-2 text-[0.78rem] text-ink transition hover:bg-surface-low"
        >
          <Bookmark className="h-3.5 w-3.5" />
          Save to note
        </button>
        <div className="flex items-center gap-4 text-ink">
          <button type="button" className="transition hover:text-primary">
            <ThumbsUp className="h-4 w-4" />
          </button>
          <button type="button" className="transition hover:text-primary">
            <ThumbsDown className="h-4 w-4" />
          </button>
          <button type="button" className="transition hover:text-primary">
            <Copy className="h-4 w-4" />
          </button>
        </div>
      </div>
    </section>
  )
}
