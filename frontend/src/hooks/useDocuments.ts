import { useCallback, useEffect, useState } from 'react'
import type { NotebookDetail, NotebookSummary, SourceItem, UserProfile } from '../types'
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

  const load = useCallback(async (options?: { silent?: boolean }) => {
    if (!options?.silent) {
      setLoading(true)
    }
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
      if (!options?.silent) {
        setNotebook(null)
      }
    } finally {
      if (!options?.silent) {
        setLoading(false)
      }
    }
  }, [notebookId, user])

  const refreshNotebook = useCallback(async () => {
    if (!notebookId) {
      return
    }

    try {
      setError(null)
      setNotebook(await documentService.getNotebookDetail(notebookId))
    } catch (err) {
      setError((err as Error).message)
    }
  }, [notebookId])

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

  useEffect(() => {
    const hasProcessingSources = notebook?.sources.some(
      (source) => source.status === 'pending' || source.status === 'processing',
    )

    if (!notebookId || !hasProcessingSources) {
      return undefined
    }

    const intervalId = window.setInterval(() => {
      void refreshNotebook()
    }, 5000)

    return () => {
      window.clearInterval(intervalId)
    }
  }, [notebook?.sources, notebookId, refreshNotebook])

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

  const renameNotebook = async (id: string, title: string) => {
    const renamed = await documentService.updateNotebook(id, { title })
    setNotebook((current) => (current?.id === id ? renamed : current))
    setSummaries((current) =>
      current.map((summary) =>
        summary.id === id
          ? {
              ...summary,
              title: renamed.title,
              updatedAt: renamed.updatedAt,
              description: renamed.description,
            }
          : summary,
      ),
    )
    return renamed
  }

  const processUploads = async (files: File[]) => {
    if (!notebookId || !files.length) {
      return
    }

    const optimisticSources: SourceItem[] = files.map((file) => ({
      id: `uploading-${file.name}-${file.size}-${file.lastModified}`,
      name: file.name.replace(/\.pdf$/i, ''),
      kind: 'pdf',
      meta: 'Indexing - queued',
      selected: false,
      status: 'pending',
    }))

    setError(null)
    setNotebook((current) =>
      current
        ? {
            ...current,
            sources: [
              ...optimisticSources.filter(
                (source) => !current.sources.some((existing) => existing.name === source.name),
              ),
              ...current.sources,
            ],
          }
        : current,
    )

    try {
      let updatedNotebook: NotebookDetail | null = notebook
      for (const file of files) {
        updatedNotebook = await documentService.uploadDocument(notebookId, file)
        if (updatedNotebook) {
          setNotebook(updatedNotebook)
        }
      }

      const [refreshedSummaries, refreshedNotebook] = await Promise.all([
        documentService.getNotebookSummaries(),
        documentService.getNotebookDetail(notebookId),
      ])
      setNotebook(refreshedNotebook)
      setSummaries(refreshedSummaries)
    } catch (err) {
      setError((err as Error).message)
      void refreshNotebook()
    }
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
    renameNotebook,
    processUploads,
    addStudioDocument,
    reload: load,
  }
}
