import { Check, Loader2, MoreVertical, PanelLeft, Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import type { SourceItem } from '../../types'

interface SourceRailProps {
  sources: SourceItem[]
  onAddSource: () => void
  onToggleSource: (name: string) => void
  onToggleAllSources: () => void
  onRenameSource?: (source: SourceItem) => void
  onDeleteSource?: (source: SourceItem) => void
}

export function SourceRail({
  sources,
  onAddSource,
  onToggleSource,
  onToggleAllSources,
  onRenameSource,
  onDeleteSource,
}: SourceRailProps) {
  const [openMenuId, setOpenMenuId] = useState<string | null>(null)
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
        {sources.map((source) => {
          const isIndexing = source.status === 'pending' || source.status === 'processing'
          const menuOpen = openMenuId === source.id

          return (
            <div
              key={source.id}
              className="group relative rounded-lg px-1 py-1 transition hover:bg-white/35"
            >
              <button
                type="button"
                disabled={source.status !== 'completed'}
                onClick={() => {
                  setOpenMenuId(null)
                  onToggleSource(source.name)
                }}
                className="block w-full pr-8 text-left transition disabled:cursor-not-allowed"
              >
                <div className="flex items-start gap-3">
                  <span
                    className={`mt-0.5 flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded-[4px] border ${
                      isIndexing
                        ? 'border-outline bg-white text-primary'
                        : source.selected
                        ? 'border-primary bg-primary text-white'
                        : 'border-outline bg-transparent text-transparent'
                    }`}
                  >
                    {isIndexing ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <Check className="h-3 w-3" strokeWidth={3} />
                    )}
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

              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation()
                  setOpenMenuId((current) => (current === source.id ? null : source.id))
                }}
                className={`absolute right-1 top-1 rounded-md p-1 text-muted transition hover:bg-white hover:text-ink ${
                  menuOpen ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus:opacity-100'
                }`}
                aria-label={`Open menu for ${source.name}`}
              >
                <MoreVertical className="h-4 w-4" />
              </button>

              {menuOpen && (
                <div className="absolute right-1 top-8 z-20 w-40 rounded-lg border border-black/8 bg-white py-1 text-[0.74rem] shadow-[0_12px_32px_rgba(43,52,55,0.16)]">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation()
                      setOpenMenuId(null)
                      onRenameSource?.(source)
                    }}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-ink transition hover:bg-surface-low"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                    Rename source
                  </button>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation()
                      setOpenMenuId(null)
                      onDeleteSource?.(source)
                    }}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-red-600 transition hover:bg-red-50"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Delete source
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </aside>
  )
}
