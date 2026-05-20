import { Headphones, Loader2, Mic, MoreVertical, Presentation, FileText, Pencil, RotateCcw, TableProperties, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { audioOverviewService } from '../../services/audioOverviewService'
import type { AudioOverviewDocument, StudioDocument, StudioNoteDocument } from '../../types'

interface StudioDocumentsPanelProps {
  documents: StudioDocument[]
  onOpenDocument?: (document: StudioDocument) => void
  onCreateAudioOverview?: () => void
  onRenameNote?: (document: StudioNoteDocument) => void
  onDeleteNote?: (document: StudioNoteDocument) => void
  onDeleteAudioOverview?: (document: AudioOverviewDocument) => void
  onRetryAudioOverview?: (document: AudioOverviewDocument) => void
  audioDisabled?: boolean
  audioBusy?: boolean
}

export function StudioDocumentsPanel({
  documents,
  onOpenDocument,
  onCreateAudioOverview,
  onRenameNote,
  onDeleteNote,
  onDeleteAudioOverview,
  onRetryAudioOverview,
  audioDisabled = false,
  audioBusy = false,
}: StudioDocumentsPanelProps) {
  const [openMenuId, setOpenMenuId] = useState<string | null>(null)
  const hasProcessingAudio = documents.some(
    (document) =>
      document.itemType === 'audio_overview' &&
      (document.status === 'pending' || document.status === 'processing'),
  )

  return (
    <aside className="flex h-full flex-col">
      <div className="mb-6">
        <h2 className="text-[0.82rem] font-semibold uppercase tracking-[0.12em] text-ink">Studio</h2>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3">
        <button
          type="button"
          onClick={onCreateAudioOverview}
          disabled={audioDisabled || audioBusy}
          className="flex min-h-22 flex-col items-center justify-center gap-3 rounded-2xl bg-white/65 px-4 py-4 text-[0.78rem] font-medium text-ink shadow-[inset_0_0_0_1px_rgba(171,179,183,0.12)] transition hover:bg-white"
        >
          {audioBusy || hasProcessingAudio ? (
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
          ) : (
            <Mic className="h-4 w-4 text-primary" />
          )}
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
        Saved Items
      </div>

      <div className="space-y-3">
        {!documents.length && (
          <div className="rounded-[10px] border border-dashed border-outline/70 px-4 py-5 text-[0.72rem] leading-5 text-muted">
            No saved items yet.
          </div>
        )}
        {documents.map((document) => {
          const Icon =
            document.itemType === 'audio_overview'
              ? Headphones
              : document.icon === 'description'
              ? FileText
              : TableProperties
          const menuOpen = openMenuId === document.id
          const audioDocument = document.itemType === 'audio_overview' ? document : null
          const noteDocument = document.itemType === 'note' ? document : null
          const isAudio = Boolean(audioDocument)
          const isAudioProcessing =
            audioDocument?.status === 'pending' || audioDocument?.status === 'processing'

          return (
            <article
              key={document.id}
              className="group relative rounded-[18px] border border-black/5 bg-white shadow-[0_8px_22px_rgba(43,52,55,0.05)] transition hover:-translate-y-0.5 hover:shadow-[0_12px_28px_rgba(43,52,55,0.08)]"
            >
              {isAudio ? (
                <div className="px-4 py-4 pr-10">
                  <div className="flex items-start gap-3">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-surface-low text-primary">
                      {isAudioProcessing ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Icon className="h-4 w-4" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <h3 className="text-[0.82rem] font-medium leading-5 text-ink">{document.title}</h3>
                      <p className="mt-1 text-[0.66rem] uppercase tracking-[0.1em] text-muted">
                        {audioDocument ? audioOverviewService.styleLabel(audioDocument.style) : 'Audio overview'}
                      </p>
                      <p className="mt-1.5 text-[0.68rem] leading-5 text-muted">{document.excerpt}</p>
                      {audioDocument?.status === 'completed' && audioDocument.audioUrl && (
                        <audio
                          controls
                          src={audioDocument.audioUrl}
                          className="mt-3 h-8 w-full"
                        />
                      )}
                      {audioDocument?.status === 'failed' && (
                        <div className="mt-2 text-[0.66rem] font-medium text-red-600">
                          Failed
                        </div>
                      )}
                      <p className="mt-2.5 text-[0.66rem] text-muted">{document.updatedAt}</p>
                    </div>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setOpenMenuId(null)
                    onOpenDocument?.(document)
                  }}
                  className="block w-full px-4 py-4 pr-10 text-left"
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
                </button>
              )}

              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation()
                  setOpenMenuId((current) => (current === document.id ? null : document.id))
                }}
                className={`absolute right-3 top-3 rounded-md p-1 text-muted transition hover:bg-surface-low hover:text-ink ${
                  menuOpen ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus:opacity-100'
                }`}
                aria-label={`Open menu for ${document.title}`}
              >
                <MoreVertical className="h-4 w-4" />
              </button>

              {menuOpen && (
                <div className="absolute right-3 top-10 z-20 w-36 rounded-lg border border-black/8 bg-white py-1 text-[0.74rem] shadow-[0_12px_32px_rgba(43,52,55,0.16)]">
                  {isAudio && audioDocument ? (
                    <>
                      {(audioDocument.status === 'failed' || audioDocument.status === 'completed') && (
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation()
                            setOpenMenuId(null)
                            onRetryAudioOverview?.(audioDocument)
                          }}
                          className="flex w-full items-center gap-2 px-3 py-2 text-left text-ink transition hover:bg-surface-low"
                        >
                          <RotateCcw className="h-3.5 w-3.5" />
                          Regenerate
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation()
                          setOpenMenuId(null)
                          onDeleteAudioOverview?.(audioDocument)
                        }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-red-600 transition hover:bg-red-50"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        Delete audio
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation()
                          setOpenMenuId(null)
                          if (noteDocument) {
                            onRenameNote?.(noteDocument)
                          }
                        }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-ink transition hover:bg-surface-low"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                        Rename note
                      </button>
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation()
                          setOpenMenuId(null)
                          if (noteDocument) {
                            onDeleteNote?.(noteDocument)
                          }
                        }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-red-600 transition hover:bg-red-50"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        Delete note
                      </button>
                    </>
                  )}
                </div>
              )}
            </article>
          )
        })}
      </div>
    </aside>
  )
}
