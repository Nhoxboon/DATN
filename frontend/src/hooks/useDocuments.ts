import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type {
  AudioOverviewDocument,
  NotebookDetail,
  NotebookSummary,
  SlideDeckDocument,
  SourceItem,
  StudioDocument,
  UserProfile,
} from '../types'
import { documentService } from '../services/documentService'
import { audioOverviewService, type AudioOverviewUrl } from '../services/audioOverviewService'
import { slideDeckService, type SlideDeckPdfUrl } from '../services/slideDeckService'
import { useAuth } from './useAuth'

function mergeStudioDocuments(
  notes: StudioDocument[],
  audioOverviews: AudioOverviewDocument[],
  slideDecks: SlideDeckDocument[],
) {
  return [...audioOverviews, ...slideDecks, ...notes].sort((left, right) => {
    const leftTime = new Date(left.sortTimestamp || '').getTime()
    const rightTime = new Date(right.sortTimestamp || '').getTime()
    return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime)
  })
}

function preserveFreshAudioUrl(
  audioOverview: AudioOverviewDocument,
  existingAudioOverviews: AudioOverviewDocument[],
) {
  const existing = existingAudioOverviews.find((document) => document.id === audioOverview.id)
  if (existing?.audioUrl) {
    return {
      ...audioOverview,
      audioUrl: existing.audioUrl,
      audioUrlExpiresAt: existing.audioUrlExpiresAt,
    }
  }

  return audioOverview
}

function preserveFreshPdfUrl(slideDeck: SlideDeckDocument, existingSlideDecks: SlideDeckDocument[]) {
  const existing = existingSlideDecks.find((document) => document.id === slideDeck.id)
  if (existing?.pdfUrl) {
    return {
      ...slideDeck,
      pdfUrl: existing.pdfUrl,
      pdfUrlExpiresAt: existing.pdfUrlExpiresAt,
    }
  }

  return slideDeck
}

function withStudioArtifacts(
  notebook: NotebookDetail | null,
  audioOverviews: AudioOverviewDocument[],
  slideDecks: SlideDeckDocument[],
  existingDocuments: StudioDocument[] = [],
) {
  if (!notebook) {
    return null
  }

  const existingAudioOverviews = existingDocuments.filter(
    (document): document is AudioOverviewDocument => document.itemType === 'audio_overview',
  )
  const existingSlideDecks = existingDocuments.filter(
    (document): document is SlideDeckDocument => document.itemType === 'slide_deck',
  )

  return {
    ...notebook,
    studioDocuments: mergeStudioDocuments(
      notebook.studioDocuments.filter((document) => document.itemType === 'note'),
      audioOverviews.map((audioOverview) => preserveFreshAudioUrl(audioOverview, existingAudioOverviews)),
      slideDecks.map((slideDeck) => preserveFreshPdfUrl(slideDeck, existingSlideDecks)),
    ),
  }
}

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
      const [summaryData, notebookData, audioOverviews, slideDecks] = await Promise.all([
        documentService.getNotebookSummaries(),
        notebookId ? documentService.getNotebookDetail(notebookId) : Promise.resolve(null),
        notebookId ? audioOverviewService.getAudioOverviews(notebookId) : Promise.resolve([]),
        notebookId ? slideDeckService.getSlideDecks(notebookId) : Promise.resolve([]),
      ])

      setProfile(userProfile)
      setSummaries(summaryData)
      setNotebook(withStudioArtifacts(notebookData, audioOverviews, slideDecks))
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
      const [notebookData, audioOverviews, slideDecks] = await Promise.all([
        documentService.getNotebookDetail(notebookId),
        audioOverviewService.getAudioOverviews(notebookId),
        slideDeckService.getSlideDecks(notebookId),
      ])
      setNotebook((current) =>
        withStudioArtifacts(
          notebookData,
          audioOverviews,
          slideDecks,
          current?.studioDocuments ?? [],
        ),
      )
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
    const hasProcessingAudio = notebook?.studioDocuments.some(
      (document) =>
        document.itemType === 'audio_overview' &&
        (document.status === 'pending' || document.status === 'processing'),
    )
    const hasProcessingSlides = notebook?.studioDocuments.some(
      (document) =>
        document.itemType === 'slide_deck' &&
        (document.status === 'pending' || document.status === 'processing'),
    )

    if (!notebookId || (!hasProcessingSources && !hasProcessingAudio && !hasProcessingSlides)) {
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
  }, [notebook?.sources, notebook?.studioDocuments, notebookId, refreshNotebook])

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
    setNotebook((current) =>
      current?.id === id
        ? withStudioArtifacts(
            renamed,
            current.studioDocuments.filter(
              (document): document is AudioOverviewDocument => document.itemType === 'audio_overview',
            ),
            current.studioDocuments.filter(
              (document): document is SlideDeckDocument => document.itemType === 'slide_deck',
            ),
            current.studioDocuments,
          )
        : current,
    )
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
    const [refreshedSummaries, audioOverviews, slideDecks] = await Promise.all([
      documentService.getNotebookSummaries(),
      audioOverviewService.getAudioOverviews(notebookId),
      slideDeckService.getSlideDecks(notebookId),
    ])
    setNotebook((current) => withStudioArtifacts(renamed, audioOverviews, slideDecks, current?.studioDocuments ?? []))
    setSummaries(refreshedSummaries)
    return renamed
  }

  const deleteSource = async (documentName: string) => {
    if (!notebookId) {
      return
    }

    await documentService.deleteDocument(notebookId, documentName)
    const [refreshedSummaries, refreshedNotebook, audioOverviews, slideDecks] = await Promise.all([
      documentService.getNotebookSummaries(),
      documentService.getNotebookDetail(notebookId),
      audioOverviewService.getAudioOverviews(notebookId),
      slideDeckService.getSlideDecks(notebookId),
    ])
    setNotebook((current) =>
      withStudioArtifacts(refreshedNotebook, audioOverviews, slideDecks, current?.studioDocuments ?? []),
    )
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
          setNotebook((current) =>
            withStudioArtifacts(
              updatedNotebook,
              current?.studioDocuments.filter(
                (document): document is AudioOverviewDocument => document.itemType === 'audio_overview',
              ) ?? [],
              current?.studioDocuments.filter(
                (document): document is SlideDeckDocument => document.itemType === 'slide_deck',
              ) ?? [],
              current?.studioDocuments ?? [],
            ),
          )
        }
      }

      const [refreshedSummaries, refreshedNotebook, audioOverviews, slideDecks] = await Promise.all([
        documentService.getNotebookSummaries(),
        documentService.getNotebookDetail(notebookId),
        audioOverviewService.getAudioOverviews(notebookId),
        slideDeckService.getSlideDecks(notebookId),
      ])
      setNotebook((current) =>
        withStudioArtifacts(refreshedNotebook, audioOverviews, slideDecks, current?.studioDocuments ?? []),
      )
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

  const createAudioOverview = async (documentNames: string[]) => {
    if (!notebookId || !documentNames.length) {
      return null
    }

    const pendingDocument = audioOverviewService.makePendingDocument(documentNames)
    setError(null)
    setNotebook((current) =>
      current
        ? {
            ...current,
            studioDocuments: [pendingDocument, ...current.studioDocuments],
          }
        : current,
    )

    try {
      const created = await audioOverviewService.createAudioOverview(notebookId, documentNames)
      setNotebook((current) =>
        current
          ? {
              ...current,
              studioDocuments: current.studioDocuments.map((document) =>
                document.id === pendingDocument.id ? created : document,
              ),
            }
          : current,
      )
      setSummaries(await documentService.getNotebookSummaries())
      return created
    } catch (err) {
      setError((err as Error).message)
      setNotebook((current) =>
        current
          ? {
              ...current,
              studioDocuments: current.studioDocuments.filter((document) => document.id !== pendingDocument.id),
            }
          : current,
      )
      return null
    }
  }

  const deleteAudioOverview = async (overviewId: string) => {
    if (!notebookId) {
      return
    }

    await audioOverviewService.deleteAudioOverview(notebookId, overviewId)
    setNotebook((current) =>
      current
        ? {
            ...current,
            studioDocuments: current.studioDocuments.filter((document) => document.id !== overviewId),
          }
        : current,
    )
    setSummaries(await documentService.getNotebookSummaries())
  }

  const refreshAudioOverviewUrl = async (overviewId: string): Promise<AudioOverviewUrl | null> => {
    if (!notebookId) {
      return null
    }

    const audio = await audioOverviewService.getAudioUrl(notebookId, overviewId)
    setNotebook((current) =>
      current
        ? {
            ...current,
            studioDocuments: current.studioDocuments.map((document) =>
              document.itemType === 'audio_overview' && document.id === overviewId
                ? {
                    ...document,
                    audioUrl: audio.audioUrl,
                    audioUrlExpiresAt: audio.expiresAt,
                  }
                : document,
            ),
          }
        : current,
    )
    return audio
  }

  const createSlideDeck = async (documentNames: string[]) => {
    if (!notebookId || !documentNames.length) {
      return null
    }

    const pendingDocument = slideDeckService.makePendingDocument(documentNames)
    setError(null)
    setNotebook((current) =>
      current
        ? {
            ...current,
            studioDocuments: [pendingDocument, ...current.studioDocuments],
          }
        : current,
    )

    try {
      const created = await slideDeckService.createSlideDeck(notebookId, documentNames)
      setNotebook((current) =>
        current
          ? {
              ...current,
              studioDocuments: current.studioDocuments.map((document) =>
                document.id === pendingDocument.id ? created : document,
              ),
            }
          : current,
      )
      setSummaries(await documentService.getNotebookSummaries())
      return created
    } catch (err) {
      setError((err as Error).message)
      setNotebook((current) =>
        current
          ? {
              ...current,
              studioDocuments: current.studioDocuments.filter((document) => document.id !== pendingDocument.id),
            }
          : current,
      )
      return null
    }
  }

  const deleteSlideDeck = async (deckId: string) => {
    if (!notebookId) {
      return
    }

    await slideDeckService.deleteSlideDeck(notebookId, deckId)
    setNotebook((current) =>
      current
        ? {
            ...current,
            studioDocuments: current.studioDocuments.filter((document) => document.id !== deckId),
          }
        : current,
    )
    setSummaries(await documentService.getNotebookSummaries())
  }

  const refreshSlideDeckPdfUrl = async (deckId: string): Promise<SlideDeckPdfUrl | null> => {
    if (!notebookId) {
      return null
    }

    const pdf = await slideDeckService.getPdfUrl(notebookId, deckId)
    setNotebook((current) =>
      current
        ? {
            ...current,
            studioDocuments: current.studioDocuments.map((document) =>
              document.itemType === 'slide_deck' && document.id === deckId
                ? {
                    ...document,
                    pdfUrl: pdf.pdfUrl,
                    pdfUrlExpiresAt: pdf.expiresAt,
                  }
                : document,
            ),
          }
        : current,
    )
    return pdf
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
    createAudioOverview,
    deleteAudioOverview,
    refreshAudioOverviewUrl,
    createSlideDeck,
    deleteSlideDeck,
    refreshSlideDeckPdfUrl,
    processUploads,
    addStudioDocument,
    reload: load,
  }
}
