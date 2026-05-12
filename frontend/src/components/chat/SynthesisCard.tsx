import { Sparkles } from 'lucide-react'
import type { NotebookDetail } from '../../types'
import { useTypewriter } from '../../hooks/useTypewriter'

export function SynthesisCard({ notebook }: { notebook: NotebookDetail }) {
  const typedBody = useTypewriter(notebook.synthesisBody, 8)

  return (
    <section className="py-2">
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
    </section>
  )
}
