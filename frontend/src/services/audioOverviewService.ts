import type {
  AudioOverviewDocument,
  BackendAudioOverview,
  BackendAudioOverviewUrl,
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

function styleLabel(style: string | null | undefined) {
  if (style === 'news_briefing') {
    return 'News briefing'
  }

  if (style === 'podcast_dialogue') {
    return 'Podcast script'
  }

  return 'Audio overview'
}

function audioExcerpt(overview: BackendAudioOverview) {
  if (overview.status === 'failed') {
    return overview.error_message || 'Audio generation failed.'
  }

  if (overview.status === 'pending') {
    return 'Queued for audio generation.'
  }

  if (overview.status === 'processing') {
    return 'Generating transcript and rendering audio.'
  }

  const script = overview.script_text?.replace(/\s+/g, ' ').slice(0, 150)
  return script ? `${script}${(overview.script_text?.length ?? 0) > 150 ? '...' : ''}` : 'Ready to play.'
}

function toAudioDocument(overview: BackendAudioOverview, audioUrl?: string | null): AudioOverviewDocument {
  return {
    id: overview.id,
    itemType: 'audio_overview',
    icon: 'audio',
    title: overview.title || 'Audio Overview',
    excerpt: audioExcerpt(overview),
    updatedAt: updatedLabel(overview.updated_at),
    sortTimestamp: overview.updated_at || overview.created_at,
    status: overview.status,
    style: overview.style,
    scriptText: overview.script_text,
    documentNames: overview.document_names,
    durationSeconds: overview.duration_seconds,
    storagePath: overview.storage_path,
    contentType: overview.content_type,
    errorMessage: overview.error_message,
    audioUrl,
  }
}

export const audioOverviewService = {
  async getAudioOverviews(notebookId: string): Promise<AudioOverviewDocument[]> {
    const data = await apiFetch<BackendAudioOverview[]>(
      `/notebooks/${encodeURIComponent(notebookId)}/audio-overviews`,
    )

    return Promise.all(
      data.map(async (overview) => {
        if (overview.status !== 'completed') {
          return toAudioDocument(overview)
        }

        try {
          const url = await this.getAudioUrl(notebookId, overview.id)
          return toAudioDocument(overview, url)
        } catch {
          return toAudioDocument(overview)
        }
      }),
    )
  },

  async createAudioOverview(notebookId: string, documentNames: string[]): Promise<AudioOverviewDocument> {
    const data = await apiFetch<BackendAudioOverview>(
      `/notebooks/${encodeURIComponent(notebookId)}/audio-overviews`,
      {
        method: 'POST',
        body: JSON.stringify({
          document_names: documentNames,
        }),
      },
    )
    return toAudioDocument(data)
  },

  async getAudioUrl(notebookId: string, overviewId: string): Promise<string> {
    const data = await apiFetch<BackendAudioOverviewUrl>(
      `/notebooks/${encodeURIComponent(notebookId)}/audio-overviews/${encodeURIComponent(overviewId)}/audio-url`,
    )
    return data.audio_url
  },

  async deleteAudioOverview(notebookId: string, overviewId: string): Promise<void> {
    await apiFetch<void>(
      `/notebooks/${encodeURIComponent(notebookId)}/audio-overviews/${encodeURIComponent(overviewId)}`,
      {
        method: 'DELETE',
      },
    )
  },

  makePendingDocument(documentNames: string[]): AudioOverviewDocument {
    const now = new Date().toISOString()
    return {
      id: `pending-audio-${Date.now()}`,
      itemType: 'audio_overview',
      icon: 'audio',
      title: 'Audio Overview',
      excerpt: 'Queued for audio generation.',
      updatedAt: 'Updated just now',
      sortTimestamp: now,
      status: 'pending',
      style: null,
      scriptText: null,
      documentNames,
      durationSeconds: null,
      storagePath: null,
      contentType: 'audio/mp4',
      errorMessage: null,
      audioUrl: null,
    }
  },

  styleLabel,
}
