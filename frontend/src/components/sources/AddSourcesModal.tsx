import { createPortal } from 'react-dom'
import { AlertCircle, FileText, Trash2, Upload, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { usePortal } from '../../hooks/usePortal'

interface AddSourcesModalProps {
  open: boolean
  onClose: () => void
  onProcess: (files: File[]) => void
}

function sizeLabel(file: File) {
  const mb = file.size / 1024 / 1024
  return `${mb.toFixed(mb >= 10 ? 0 : 1)} MB`
}

function isSupportedDocument(file: File) {
  const name = file.name.toLowerCase()
  return name.endsWith('.pdf') || name.endsWith('.docx')
}

export function AddSourcesModal({ open, onClose, onProcess }: AddSourcesModalProps) {
  const portalTarget = usePortal()
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [files, setFiles] = useState<File[]>([])
  const [error, setError] = useState<string | null>(null)

  if (!open || !portalTarget) {
    return null
  }

  const addFiles = (nextFiles: FileList | null) => {
    if (!nextFiles) {
      return
    }

    const documents = Array.from(nextFiles).filter(isSupportedDocument)
    setFiles((current) => {
      const existing = new Set(current.map((file) => `${file.name}:${file.size}`))
      return [...current, ...documents.filter((file) => !existing.has(`${file.name}:${file.size}`))]
    })
    setError(documents.length === nextFiles.length ? null : 'Only PDF and DOCX files are supported.')
  }

  const removeFile = (file: File) => {
    setFiles((current) => current.filter((item) => item !== file))
  }

  const handleProcess = () => {
    setError(null)

    onProcess(files)
    setFiles([])
  }

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(12,15,16,0.2)] px-4 py-10 backdrop-blur-[3px]">
      <div className="w-full max-w-[760px] overflow-hidden rounded-[14px] bg-white shadow-[0_24px_80px_rgba(43,52,55,0.18)]">
        <div className="border-b border-black/8 px-6 py-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-[1.55rem] font-medium text-ink">Add Sources</h2>
              <p className="mt-1 text-[0.76rem] text-muted">
                Upload PDF or Word documents to this notebook.
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
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.pdf,.docx"
            multiple
            className="hidden"
            onChange={(event) => {
              addFiles(event.target.files)
              event.target.value = ''
            }}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="w-full rounded-[8px] border border-dashed border-outline/70 bg-surface-low/45 px-6 py-7 text-center transition hover:bg-surface-low"
          >
            <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-[10px] bg-[rgba(0,91,192,0.12)] text-primary">
              <Upload className="h-4.5 w-4.5" />
            </div>
            <h3 className="text-[0.96rem] font-medium text-ink">Choose documents</h3>
            <p className="mt-1 text-[0.66rem] text-muted">Max 50MB per file</p>
          </button>

          <div className="mt-5">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-[0.68rem] font-semibold uppercase tracking-[0.1em] text-muted">
                Selected Files ({files.length})
              </div>
              <div className="text-[0.62rem] text-primary">{files.length ? 'Ready to index' : 'No files selected'}</div>
            </div>

            <div className="space-y-2 rounded-[8px] bg-surface-low/45 p-2">
              {files.map((file) => (
                <div
                  key={`${file.name}:${file.size}`}
                  className="flex w-full items-center gap-3 rounded-[8px] border border-transparent bg-white px-3 py-2.5 text-left shadow-[0_2px_10px_rgba(43,52,55,0.05)]"
                >
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] bg-surface-low text-primary">
                    <FileText className="h-3.5 w-3.5" />
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[0.74rem] font-medium text-ink">{file.name}</div>
                  </div>

                  <div className="text-[0.64rem] text-muted">{sizeLabel(file)}</div>

                  <button
                    type="button"
                    onClick={() => removeFile(file)}
                    className="ml-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-[4px] text-muted transition hover:bg-surface-low hover:text-ink"
                    aria-label={`Delete ${file.name}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-3 border-t border-black/8 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className={`flex items-center gap-2 text-[0.64rem] ${error ? 'text-red-600' : 'text-muted'}`}>
            <AlertCircle className="h-3.5 w-3.5" />
            <span>{error || 'Files will be indexed for AI search automatically.'}</span>
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
              disabled={!files.length}
              className="inline-flex h-8 items-center justify-center rounded-[8px] bg-primary px-4 text-[0.68rem] font-semibold text-white transition hover:brightness-105 disabled:opacity-60"
            >
              Process Sources
            </button>
          </div>
        </div>
      </div>
    </div>,
    portalTarget,
  )
}