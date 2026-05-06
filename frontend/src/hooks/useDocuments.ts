import { useEffect, useState } from 'react'
import type { NotebookDetail, NotebookSummary, UploadCandidate, UserProfile } from '../types'
import { documentService } from '../services/documentService'
import { buildUserProfile } from '../services/authService'
import { useAuth } from './useAuth'

export function useDocuments(notebookId?: string) {
  const { user } = useAuth()
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
        Promise.resolve(buildUserProfile(user)),
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
  }, [notebookId, user])

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
