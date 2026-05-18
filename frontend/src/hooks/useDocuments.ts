import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { NotebookDetail, NotebookSummary, SourceItem, UserProfile } from '../types'
import { documentService } from '../services/documentService'
import { useAuth } from './useAuth'

export function useDocuments(notebookId?: string) {
  const { user } = useAuth()
  const [loading, setLoading] = useState(true)
  const [summaries, setSummaries] = useState<NotebookSummary[]>([])
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [notebook, setNotebook] = useState<NotebookDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const hasLoadedRef = useRef(false)
  const loadScopeRef = useRef('')
  const userId = user?.id ?? null
  const userEmail = user?.email ?? null
  const userFullName =
    typeof user?.user_metadata.full_name === 'string' ? user.user_metadata.full_name : null
  const userName =
    typeof user?.user_metadata.name === 'string' ? user.user_metadata.name : null
  const userProfile = useMemo<UserProfile | null>(() => {
    if (!userId) {
      return null
    }

    const fullName = userFullName || userName || userEmail?.split('@')[0] || 'Scholar'
    const avatarLabel = fullName
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join('')
      .padEnd(2, 'S')
      .slice(0, 2)

    return {
      id: userId,
      name: fullName,
      role: userEmail || 'Research workspace',
      avatarLabel,
    }
  }, [userEmail, userFullName, userId, userName])

  const load = useCallback(async (options?: { silent?: boolean }) => {
    const loadScope = `${userId ?? 'anonymous'}:${notebookId ?? 'dashboard'}`
    if (loadScopeRef.current !== loadScope) {
      loadScopeRef.current = loadScope
      hasLoadedRef.current = false
    }

    const isBlockingLoad = !options?.silent && !hasLoadedRef.current

    if (isBlockingLoad) {
      setLoading(true)
      setNotebook(null)
    }
    setError(null)

    try {
      const [summaryData, notebookData] = await Promise.all([
        documentService.getNotebookSummaries(),
        notebookId ? documentService.getNotebookDetail(notebookId) : Promise.resolve(null),
      ])

      setProfile(userProfile)
      setSummaries(summaryData)
      setNotebook(notebookData)
    } catch (err) {
      setError((err as Error).message)
      if (isBlockingLoad) {
        setNotebook(null)
      }
    } finally {
      if (!options?.silent) {
        hasLoadedRef.current = true
      }
      if (!options?.silent) {
        setLoading(false)
      }
    }
  }, [notebookId, userId, userProfile])

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
      if (document.visibilityState === 'visible') {
        void refreshNotebook()
      }
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

  const renameSource = async (documentName: string, nextDocumentName: string) => {
    if (!notebookId) {
      return null
    }

    const renamed = await documentService.renameDocument(notebookId, documentName, nextDocumentName)
    const refreshedSummaries = await documentService.getNotebookSummaries()
    setNotebook(renamed)
    setSummaries(refreshedSummaries)
    return renamed
  }

  const deleteSource = async (documentName: string) => {
    if (!notebookId) {
      return
    }

    await documentService.deleteDocument(notebookId, documentName)
    const [refreshedSummaries, refreshedNotebook] = await Promise.all([
      documentService.getNotebookSummaries(),
      documentService.getNotebookDetail(notebookId),
    ])
    setNotebook(refreshedNotebook)
    setSummaries(refreshedSummaries)
  }

  const renameNote = async (noteId: string, title: string) => {
    if (!notebookId) {
      return null
    }

    const renamed = await documentService.renameNote(notebookId, noteId, title)
    setNotebook((current) =>
      current
        ? {
            ...current,
            studioDocuments: current.studioDocuments.map((document) =>
              document.id === noteId ? renamed : document,
            ),
          }
        : current,
    )
    setSummaries(await documentService.getNotebookSummaries())
    return renamed
  }

  const deleteNote = async (noteId: string) => {
    if (!notebookId) {
      return
    }

    await documentService.deleteNote(notebookId, noteId)
    setNotebook((current) =>
      current
        ? {
            ...current,
            studioDocuments: current.studioDocuments.filter((document) => document.id !== noteId),
          }
        : current,
    )
    setSummaries(await documentService.getNotebookSummaries())
  }

  const processUploads = async (files: File[]) => {
    if (!notebookId || !files.length) {
      return
    }

    const optimisticSources: SourceItem[] = files.map((file) => ({
      id: `uploading-${file.name}-${file.size}-${file.lastModified}`,
      name: file.name.replace(/\.(pdf|docx)$/i, ''),
      kind: file.name.toLowerCase().endsWith('.docx') ? 'docx' : 'pdf',
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
    renameSource,
    deleteSource,
    renameNote,
    deleteNote,
    processUploads,
    addStudioDocument,
    reload: load,
  }
}
