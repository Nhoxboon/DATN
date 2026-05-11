import { useCallback, useEffect, useState } from 'react'
import type { NotebookDetail, NotebookSummary, UserProfile } from '../types'
import { documentService } from '../services/documentService'
import { buildUserProfile } from '../services/authService'
import { useAuth } from './useAuth'

export function useDocuments(notebookId?: string) {
  const { user } = useAuth()
  const [loading, setLoading] = useState(true)
  const [summaries, setSummaries] = useState<NotebookSummary[]>([])
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [notebook, setNotebook] = useState<NotebookDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      const [summaryData, notebookData] = await Promise.all([
        documentService.getNotebookSummaries(),
        notebookId ? documentService.getNotebookDetail(notebookId) : Promise.resolve(null),
      ])

      setProfile(buildUserProfile(user))
      setSummaries(summaryData)
      setNotebook(notebookData)
    } catch (err) {
      setError((err as Error).message)
      setNotebook(null)
    } finally {
      setLoading(false)
    }
  }, [notebookId, user])

  useEffect(() => {
    let cancelled = false

    async function loadIfCurrent() {
      await load()
      if (cancelled) {
        return
      }
    }

    void loadIfCurrent()

    return () => {
      cancelled = true
    }
  }, [load])

  const createNotebook = async () => {
    const created = await documentService.createNotebook()
    const refreshedSummaries = await documentService.getNotebookSummaries()
    setSummaries(refreshedSummaries)
    return created
  }

  const deleteNotebook = async (id: string) => {
    await documentService.deleteNotebook(id)
    setSummaries((current) => current.filter((summary) => summary.id !== id))
  }

  const processUploads = async (files: File[]) => {
    if (!notebookId || !files.length) {
      return
    }

    let updatedNotebook: NotebookDetail | null = notebook
    for (const file of files) {
      updatedNotebook = await documentService.uploadDocument(notebookId, file)
    }

    const refreshedSummaries = await documentService.getNotebookSummaries()
    setNotebook(updatedNotebook)
    setSummaries(refreshedSummaries)
  }

  const addStudioDocument = (document: NotebookDetail['studioDocuments'][number]) => {
    setNotebook((current) =>
      current
        ? {
            ...current,
            studioDocuments: [document, ...current.studioDocuments],
          }
        : current,
    )
  }

  return {
    loading,
    error,
    summaries,
    profile,
    notebook,
    createNotebook,
    deleteNotebook,
    processUploads,
    addStudioDocument,
    reload: load,
  }
}
