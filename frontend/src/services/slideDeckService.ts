import type { BackendSlideDeck, BackendSlideDeckUrl, SlideDeckDocument } from '../types'
import { apiFetch } from './api'

export interface SlideDeckPdfUrl {
  pdfUrl: string
  expiresAt: number
}

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

function sourceLabel(sourceCount: number) {
  return `Based on ${sourceCount} source${sourceCount === 1 ? '' : 's'}`
}

function deckExcerpt(deck: BackendSlideDeck) {
  if (deck.status === 'failed') {
    return deck.error_message || 'Presentation generation failed.'
  }

  if (deck.status === 'pending') {
    return 'Queued for presentation generation.'
  }

  if (deck.status === 'processing') {
    return 'Generating concise slides and rendering PDF.'
  }

  const slideCount = deck.deck_json?.slide_count || deck.deck_json?.slides?.length || 0
  return slideCount ? `${slideCount} slides ready.` : 'Presentation ready.'
}

function toSlideDeckDocument(deck: BackendSlideDeck, pdf?: SlideDeckPdfUrl | null): SlideDeckDocument {
  const sourceCount = deck.source_count || deck.document_names.length
  return {
    id: deck.id,
    itemType: 'slide_deck',
    icon: 'presentation',
    title: deck.title || deck.deck_json?.title || 'Presentation',
    excerpt: deckExcerpt(deck),
    updatedAt: updatedLabel(deck.updated_at),
    sortTimestamp: deck.updated_at || deck.created_at,
    status: deck.status,
    deckJson: deck.deck_json,
    documentNames: deck.document_names,
    sourceCount,
    storagePath: deck.storage_path,
    contentType: deck.content_type,
    errorMessage: deck.error_message,
    pdfUrl: pdf?.pdfUrl ?? null,
    pdfUrlExpiresAt: pdf?.expiresAt ?? null,
  }
}

export const slideDeckService = {
  async getSlideDecks(notebookId: string): Promise<SlideDeckDocument[]> {
    const data = await apiFetch<BackendSlideDeck[]>(`/notebooks/${encodeURIComponent(notebookId)}/slides`)

    return Promise.all(
      data.map(async (deck) => {
        if (deck.status !== 'completed') {
          return toSlideDeckDocument(deck)
        }

        try {
          const pdf = await this.getPdfUrl(notebookId, deck.id)
          return toSlideDeckDocument(deck, pdf)
        } catch {
          return toSlideDeckDocument(deck)
        }
      }),
    )
  },

  async createSlideDeck(notebookId: string, documentNames: string[]): Promise<SlideDeckDocument> {
    const data = await apiFetch<BackendSlideDeck>(`/notebooks/${encodeURIComponent(notebookId)}/slides`, {
      method: 'POST',
      body: JSON.stringify({
        document_names: documentNames,
      }),
    })
    return toSlideDeckDocument(data)
  },

  async getPdfUrl(notebookId: string, deckId: string): Promise<SlideDeckPdfUrl> {
    const requestedAt = Date.now()
    const data = await apiFetch<BackendSlideDeckUrl>(
      `/notebooks/${encodeURIComponent(notebookId)}/slides/${encodeURIComponent(deckId)}/pdf-url`,
    )
    return {
      pdfUrl: data.pdf_url,
      expiresAt: requestedAt + data.expires_in * 1000,
    }
  },

  async deleteSlideDeck(notebookId: string, deckId: string): Promise<void> {
    await apiFetch<void>(`/notebooks/${encodeURIComponent(notebookId)}/slides/${encodeURIComponent(deckId)}`, {
      method: 'DELETE',
    })
  },

  makePendingDocument(documentNames: string[]): SlideDeckDocument {
    const now = new Date().toISOString()
    return {
      id: `pending-slide-${Date.now()}`,
      itemType: 'slide_deck',
      icon: 'presentation',
      title: 'Presentation',
      excerpt: 'Queued for presentation generation.',
      updatedAt: 'Updated just now',
      sortTimestamp: now,
      status: 'pending',
      deckJson: null,
      documentNames,
      sourceCount: documentNames.length,
      storagePath: null,
      contentType: 'application/pdf',
      errorMessage: null,
      pdfUrl: null,
      pdfUrlExpiresAt: null,
    }
  },

  sourceLabel,
}
