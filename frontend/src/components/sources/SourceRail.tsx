import { Check, PanelLeft, Plus } from 'lucide-react'
import type { SourceItem } from '../../types'

interface SourceRailProps {
  sources: SourceItem[]
  onAddSource: () => void
  onToggleSource: (name: string) => void
  onToggleAllSources: () => void
}

export function SourceRail({ sources, onAddSource, onToggleSource, onToggleAllSources }: SourceRailProps) {
  const completedSources = sources.filter((source) => source.status === 'completed')
  const allCompletedSelected = completedSources.length > 0 && completedSources.every((source) => source.selected)

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

      <button
        type="button"
        disabled={!completedSources.length}
        onClick={onToggleAllSources}
        className="mb-5 flex w-full items-center justify-between text-left text-[0.78rem] text-ink transition disabled:cursor-not-allowed disabled:text-muted"
      >
        <span>Select all sources</span>
        <span className={`flex h-4.5 w-4.5 items-center justify-center rounded-[4px] ${
          allCompletedSelected ? 'bg-primary text-white' : 'bg-transparent text-transparent ring-1 ring-outline'
        }`}>
          <Check className="h-3 w-3" strokeWidth={3} />
        </span>
      </button>

      <div className="space-y-4">
        {sources.map((source) => (
          <button
            key={source.id}
            type="button"
            disabled={source.status !== 'completed'}
            onClick={() => onToggleSource(source.name)}
            className="block w-full rounded-lg px-1 py-1 text-left transition disabled:cursor-not-allowed"
          >
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
                {source.status !== 'completed' ? (
                  <div className={`mt-1 text-[0.72rem] ${
                    source.status === 'failed' ? 'text-red-600' : 'text-muted'
                  }`}>
                    {source.status === 'failed' ? 'Failed Source' : 'Indexing Source'}
                  </div>
                ) : !source.selected && (
                  <div className="mt-1 text-[0.72rem] text-muted">Unselected Source</div>
                )}
              </div>
            </div>
          </button>
        ))}
      </div>
    </aside>
  )
}
