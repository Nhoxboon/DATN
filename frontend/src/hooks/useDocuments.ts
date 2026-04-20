import { useEffect, useState } from 'react'
import type { NotebookDetail, NotebookSummary, UploadCandidate, UserProfile } from '../types'
import { documentService } from '../services/documentService'

export function useDocuments(notebookId?: string) {
  const [loading, setLoading] = useState(true)
  const [summaries, setSummaries] = useState<NotebookSummary[]>([])
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [notebook, setNotebook] = useState<NotebookDetail | null>(null)
  const [uploadPool, setUploadPool] = useState<UploadCandidate[]>([])

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)

      const [profileData, summaryData, uploadData, notebookData] = await Promise.all([
        documentService.getProfile(),
        documentService.getNotebookSummaries(),
        documentService.getUploadCandidates(),
        notebookId ? documentService.getNotebookDetail(notebookId) : Promise.resolve(null),
      ])

      if (cancelled) {
        return
      }

      setProfile(profileData)
      setSummaries(summaryData)
      setUploadPool(uploadData)
      setNotebook(notebookData)
      setLoading(false)
    }

    void load()

    return () => {
      cancelled = true
    }
  }, [notebookId])

  const processUploads = async (uploadIds: string[]) => {
    if (!notebookId) {
      return
    }

    const updatedNotebook = await documentService.addSources(notebookId, uploadIds)
    const refreshedSummaries = await documentService.getNotebookSummaries()

    setNotebook(updatedNotebook)
    setSummaries(refreshedSummaries)
  }

  return {
    loading,
    summaries,
    profile,
    notebook,
    uploadPool,
    processUploads,
  }
}
