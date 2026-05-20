import type {
  BackendDocumentStatus,
  BackendNotebookDetail,
  BackendNotebookNote,
  BackendNotebookSummary,
  NotebookDetail,
  NotebookSummary,
  SourceItem,
  StudioDocument,
} from '../types'
import { apiFetch } from './api'

function updatedLabel(value: string | null | undefined) {
  if (!value) {
    return 'Updated just now'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'Updated just now'
  }

  return `Updated ${date.toLocaleDateString(undefined, {
    month: 'short',
    day: '2-digit',
    year: 'numeric',
  })}`
}

function statusMeta(document: BackendDocumentStatus) {
  if (document.status === 'completed') {
    const chunks = document.total_chunks ?? document.processed_chunks
    return chunks ? `Document - ${chunks} chunks indexed` : 'Document - Indexed'
  }

  if (document.status === 'failed') {
    return document.error_message || 'Indexing failed'
  }

  const processed = document.processed_chunks ?? 0
  const total = document.total_chunks ?? '?'
  return `Indexing - ${processed}/${total} chunks`
}

function toSource(document: BackendDocumentStatus): SourceItem {
  return {
    id: document.id || document.document_name,
    name: document.document_name,
    kind: 'pdf',
    meta: statusMeta(document),
    selected: document.status === 'completed',
    status: document.status,
    errorMessage: document.error_message,
  }
}

function toNote(note: BackendNotebookNote): StudioDocument {
  const excerpt = note.answer.replace(/\s+/g, ' ').slice(0, 150)

  return {
    id: note.id,
    itemType: 'note',
    icon: 'description',
    title: note.question,
    excerpt: excerpt ? `${excerpt}${note.answer.length > 150 ? '...' : ''}` : 'Saved AI answer',
    updatedAt: updatedLabel(note.updated_at),
    sortTimestamp: note.updated_at || note.created_at,
    question: note.question,
    answer: note.answer,
    sources: note.sources,
    documentNames: note.document_names,
  }
}

function toSummary(summary: BackendNotebookSummary): NotebookSummary {
  return {
    id: summary.id,
    category: 'Research Studio',
    title: summary.title,
    sourceCount: summary.source_count,
    updatedAt: updatedLabel(summary.updated_at),
    description: summary.description || 'Notebook workspace for selected research sources.',
  }
}

function toDetail(detail: BackendNotebookDetail): NotebookDetail {
  const summary = toSummary(detail)
  const completedCount = detail.documents.filter((document) => document.status === 'completed').length

  return {
    ...summary,
    sourceCount: completedCount,
    synthesisTitle: completedCount ? 'Notebook Context Ready' : 'Add Sources',
    synthesisBody: completedCount
      ? 'Ask a question about the selected sources. The answer will cite the documents that are checked in the source rail.'
      : 'Upload PDF or Word sources to this notebook, then select the documents you want the assistant to scan.',
    synthesisBullets: completedCount
      ? [
          'Checked sources define the retrieval scope for each answer.',
          'Chat history is saved until you start a new chat.',
          'Use "Save to note" to preserve important answers in Studio.',
        ]
      : [
          'Upload one or more PDF or Word documents.',
          'Wait until indexing is completed.',
          'Select completed sources before asking a question.',
        ],
    sources: detail.documents.map(toSource),
    studioDocuments: detail.notes.map(toNote),
  }
}

export const documentService = {
  async getNotebookSummaries(): Promise<NotebookSummary[]> {
    const data = await apiFetch<BackendNotebookSummary[]>('/notebooks')
    return data.map(toSummary)
  },

  async createNotebook(title = 'Untitled Notebook'): Promise<NotebookDetail> {
    const data = await apiFetch<BackendNotebookDetail>('/notebooks', {
      method: 'POST',
      body: JSON.stringify({ title }),
    })
    return toDetail(data)
  },

  async deleteNotebook(notebookId: string): Promise<void> {
    await apiFetch<void>(`/notebooks/${encodeURIComponent(notebookId)}`, {
      method: 'DELETE',
    })
  },

  async updateNotebook(notebookId: string, payload: { title?: string; description?: string | null }): Promise<NotebookDetail> {
    const data = await apiFetch<BackendNotebookDetail>(`/notebooks/${encodeURIComponent(notebookId)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    })
    return toDetail(data)
  },

  async getNotebookDetail(notebookId: string): Promise<NotebookDetail | null> {
    const data = await apiFetch<BackendNotebookDetail>(`/notebooks/${encodeURIComponent(notebookId)}`)
    return toDetail(data)
  },

  async uploadDocument(notebookId: string, file: File): Promise<NotebookDetail | null> {
    const formData = new FormData()
    formData.append('file', file)

    await apiFetch(`/notebooks/${encodeURIComponent(notebookId)}/documents/upload`, {
      method: 'POST',
      body: formData,
    })

    return this.getNotebookDetail(notebookId)
  },

  async renameDocument(notebookId: string, documentName: string, nextDocumentName: string): Promise<NotebookDetail> {
    const data = await apiFetch<BackendNotebookDetail>(
      `/notebooks/${encodeURIComponent(notebookId)}/documents/rename`,
      {
        method: 'POST',
        body: JSON.stringify({
          current_document_name: documentName,
          document_name: nextDocumentName,
        }),
      },
    )
    return toDetail(data)
  },

  async deleteDocument(notebookId: string, documentName: string): Promise<void> {
    await apiFetch<void>(
      `/notebooks/${encodeURIComponent(notebookId)}/documents/${encodeURIComponent(documentName)}`,
      {
        method: 'DELETE',
      },
    )
  },

  async getNotes(notebookId: string): Promise<StudioDocument[]> {
    const data = await apiFetch<BackendNotebookNote[]>(`/notebooks/${encodeURIComponent(notebookId)}/notes`)
    return data.map(toNote)
  },

  async renameNote(notebookId: string, noteId: string, title: string): Promise<StudioDocument> {
    const data = await apiFetch<BackendNotebookNote>(
      `/notebooks/${encodeURIComponent(notebookId)}/notes/${encodeURIComponent(noteId)}`,
      {
        method: 'PATCH',
        body: JSON.stringify({ question: title }),
      },
    )
    return toNote(data)
  },

  async deleteNote(notebookId: string, noteId: string): Promise<void> {
    await apiFetch<void>(`/notebooks/${encodeURIComponent(notebookId)}/notes/${encodeURIComponent(noteId)}`, {
      method: 'DELETE',
    })
  },
}
