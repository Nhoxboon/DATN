import { notebookDetails, notebookSummaries, uploadCandidates, userProfile } from '../data/mockData'
import type { NotebookDetail, NotebookSummary, UploadCandidate, UserProfile } from '../types'
import { withDelay } from './api'

const detailStore = structuredClone(notebookDetails) as Record<string, NotebookDetail>

function cloneDetail(detail: NotebookDetail) {
  return structuredClone(detail) as NotebookDetail
}

export const documentService = {
  async getProfile(): Promise<UserProfile> {
    return withDelay(structuredClone(userProfile))
  },

  async getNotebookSummaries(): Promise<NotebookSummary[]> {
    const refreshed = notebookSummaries.map((summary) => {
      const detail = detailStore[summary.id]

      return {
        ...summary,
        sourceCount: detail?.sources.length ?? summary.sourceCount,
      }
    })

    return withDelay(refreshed)
  },

  async getNotebookDetail(notebookId: string): Promise<NotebookDetail | null> {
    const detail = detailStore[notebookId]

    return withDelay(detail ? cloneDetail(detail) : null)
  },

  async getUploadCandidates(): Promise<UploadCandidate[]> {
    return withDelay(structuredClone(uploadCandidates))
  },

  async addSources(notebookId: string, uploadIds: string[]): Promise<NotebookDetail | null> {
    const detail = detailStore[notebookId]

    if (!detail) {
      return withDelay(null)
    }

    const selectedUploads = uploadCandidates.filter((upload) => uploadIds.includes(upload.id))
    const existingNames = new Set(detail.sources.map((source) => source.name))

    for (const upload of selectedUploads) {
      if (existingNames.has(upload.name)) {
        continue
      }

      detail.sources.unshift({
        id: `${notebookId}-${upload.id}`,
        name: upload.name,
        kind: upload.kind,
        meta:
          upload.kind === 'docx'
            ? `Word Doc • ${upload.sizeLabel}`
            : `PDF Document • ${upload.sizeLabel}`,
        selected: true,
      })
    }

    detail.sourceCount = detail.sources.length
    return withDelay(cloneDetail(detail))
  },
}
