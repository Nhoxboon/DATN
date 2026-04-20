import { createPortal } from 'react-dom'
import { AlertCircle, FileText, Trash2, Upload, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { UploadCandidate } from '../../types'
import { usePortal } from '../../hooks/usePortal'

interface AddSourcesModalProps {
  open: boolean
  uploads: UploadCandidate[]
  onClose: () => void
  onProcess: (uploadIds: string[]) => Promise<void>
}

export function AddSourcesModal({ open, uploads, onClose, onProcess }: AddSourcesModalProps) {
  const portalTarget = usePortal()
  const [selectedIds, setSelectedIds] = useState(() => uploads.map((upload) => upload.id))
  const [isProcessing, setIsProcessing] = useState(false)

  const selectedUploads = useMemo(
    () => uploads.filter((upload) => selectedIds.includes(upload.id)),
    [selectedIds, uploads],
  )

  if (!open || !portalTarget) {
    return null
  }

  const removeUpload = (uploadId: string) => {
    setSelectedIds((current) => current.filter((id) => id !== uploadId))
  }

  const handleProcess = async () => {
    setIsProcessing(true)
    await onProcess(selectedIds)
    setIsProcessing(false)
  }

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(12,15,16,0.2)] px-4 py-10 backdrop-blur-[3px]">
      <div className="w-full max-w-[760px] overflow-hidden rounded-[14px] bg-white shadow-[0_24px_80px_rgba(43,52,55,0.18)]">
        <div className="border-b border-black/8 px-6 py-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-[1.55rem] font-medium text-ink">Add Sources</h2>
              <p className="mt-1 text-[0.76rem] text-muted">
                Upload research papers, transcripts, or notes to your workspace.
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1 text-muted transition hover:bg-surface-low hover:text-ink"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="px-6 py-5">
          <div className="rounded-[8px] border border-dashed border-outline/70 bg-surface-low/45 px-6 py-7 text-center">
            <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-[10px] bg-[rgba(0,91,192,0.12)] text-primary">
              <Upload className="h-4.5 w-4.5" />
            </div>
            <h3 className="text-[0.96rem] font-medium text-ink">Drag &amp; drop files here</h3>
            <p className="mt-1 text-[0.66rem] text-muted">PDF, DOCX, or TXT (Max 50MB per file)</p>
            <button
              type="button"
              className="mt-4 inline-flex h-8 items-center justify-center rounded-[8px] bg-primary px-4 text-[0.68rem] font-semibold text-white transition hover:brightness-105"
            >
              Browse Computer
            </button>
          </div>

          <div className="mt-5">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-[0.68rem] font-semibold uppercase tracking-[0.1em] text-muted">
                Uploaded Files ({selectedUploads.length})
              </div>
              <div className="text-[0.62rem] text-primary">All files ready</div>
            </div>

            <div className="space-y-2 rounded-[8px] bg-surface-low/45 p-2">
              {selectedUploads.map((upload) => {
                return (
                  <div
                    key={upload.id}
                    className="flex w-full items-center gap-3 rounded-[8px] border border-transparent bg-white px-3 py-2.5 text-left shadow-[0_2px_10px_rgba(43,52,55,0.05)]"
                  >
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] bg-surface-low text-primary">
                      <FileText className="h-3.5 w-3.5" />
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[0.74rem] font-medium text-ink">{upload.name}</div>
                    </div>

                    <div className="text-[0.64rem] text-muted">{upload.sizeLabel}</div>

                    <button
                      type="button"
                      onClick={() => removeUpload(upload.id)}
                      className="ml-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-[4px] text-muted transition hover:bg-surface-low hover:text-ink"
                      aria-label={`Delete ${upload.name}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-3 border-t border-black/8 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 text-[0.64rem] text-muted">
            <AlertCircle className="h-3.5 w-3.5" />
            <span>Files will be indexed for AI search automatically.</span>
          </div>

          <div className="flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-[8px] px-3 py-2 text-[0.72rem] text-ink transition hover:bg-surface-low"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleProcess}
              disabled={!selectedIds.length || isProcessing}
              className="inline-flex h-8 items-center justify-center rounded-[8px] bg-primary px-4 text-[0.68rem] font-semibold text-white transition hover:brightness-105 disabled:opacity-60"
            >
              {isProcessing ? 'Processing...' : 'Process Sources'}
            </button>
          </div>
        </div>
      </div>
    </div>,
    portalTarget,
  )
}
