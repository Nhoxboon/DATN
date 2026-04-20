import { Check, PanelLeft, Plus } from 'lucide-react'
import type { SourceItem } from '../../types'

interface SourceRailProps {
  sources: SourceItem[]
  onAddSource: () => void
}

export function SourceRail({ sources, onAddSource }: SourceRailProps) {
  return (
    <aside className="flex h-full flex-col">
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-[0.82rem] font-semibold uppercase tracking-[0.12em] text-ink">Sources</h2>
        <button type="button" className="rounded-sm p-1 text-muted transition hover:text-ink">
          <PanelLeft className="h-4 w-4" />
        </button>
      </div>

      <button
        type="button"
        onClick={onAddSource}
        className="mb-6 flex h-12 w-full items-center justify-center gap-2 rounded-[14px] border border-dashed border-outline bg-white/45 text-sm font-medium text-primary transition hover:bg-white"
      >
        <Plus className="h-4 w-4" />
        Add Source
      </button>

      <div className="mb-5 flex items-center justify-between text-[0.78rem] text-ink">
        <span>Select all sources</span>
        <span className="flex h-4.5 w-4.5 items-center justify-center rounded-[4px] bg-primary text-white">
          <Check className="h-3 w-3" strokeWidth={3} />
        </span>
      </div>

      <div className="space-y-4">
        {sources.map((source) => (
          <article key={source.id} className="rounded-lg px-1 py-1 transition">
            <div className="flex items-start gap-3">
              <span
                className={`mt-0.5 flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded-[4px] border ${
                  source.selected
                    ? 'border-primary bg-primary text-white'
                    : 'border-outline bg-transparent text-transparent'
                }`}
              >
                <Check className="h-3 w-3" strokeWidth={3} />
              </span>
              <div className="min-w-0">
                <div
                  className={`truncate text-[0.94rem] font-medium ${
                    source.selected ? 'text-ink' : 'text-muted'
                  }`}
                >
                  {source.name}
                </div>
                <div className="mt-1 text-[0.76rem] leading-5 text-muted">{source.meta}</div>
                {!source.selected && (
                  <div className="mt-1 text-[0.72rem] text-muted">Unselected Source</div>
                )}
              </div>
            </div>
          </article>
        ))}
      </div>
    </aside>
  )
}
