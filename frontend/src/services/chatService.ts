import type {
  BackendChatCurrent,
  BackendChatMessage,
  BackendChatSendResponse,
  BackendNotebookNote,
  ChatMessage,
  RagSource,
  StudioDocument,
} from '../types'
import { apiFetch } from './api'

function timeLabel(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'Just now'
  }

  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function toMessage(message: BackendChatMessage): ChatMessage | null {
  if (message.role === 'system') {
    return null
  }

  return {
    id: message.id,
    role: message.role,
    content: message.content,
    timestamp: timeLabel(message.created_at),
    sources: message.sources,
  }
}

function toMessages(messages: BackendChatMessage[]) {
  return messages.map(toMessage).filter((message): message is ChatMessage => Boolean(message))
}

function toStudioDocument(note: BackendNotebookNote): StudioDocument {
  const excerpt = note.answer.replace(/\s+/g, ' ').slice(0, 150)

  return {
    id: note.id,
    icon: 'description',
    title: note.question,
    excerpt: excerpt ? `${excerpt}${note.answer.length > 150 ? '...' : ''}` : 'Saved AI answer',
    updatedAt: 'Saved just now',
    question: note.question,
    answer: note.answer,
    sources: note.sources,
    documentNames: note.document_names,
  }
}

export const chatService = {
  async getConversation(notebookId: string): Promise<ChatMessage[]> {
    const data = await apiFetch<BackendChatCurrent>(
      `/notebooks/${encodeURIComponent(notebookId)}/chat/current`,
    )
    return toMessages(data.messages)
  },

  async sendMessage(
    notebookId: string,
    input: string,
    documentNames: string[],
  ): Promise<ChatMessage[]> {
    const data = await apiFetch<BackendChatSendResponse>(
      `/notebooks/${encodeURIComponent(notebookId)}/chat/messages`,
      {
        method: 'POST',
        body: JSON.stringify({
          message: input,
          document_names: documentNames,
        }),
      },
    )

    return toMessages(data.messages)
  },

  async newChat(notebookId: string): Promise<ChatMessage[]> {
    const data = await apiFetch<BackendChatCurrent>(
      `/notebooks/${encodeURIComponent(notebookId)}/chat/new`,
      {
        method: 'POST',
      },
    )
    return toMessages(data.messages)
  },

  async saveNote(
    notebookId: string,
    question: string,
    answer: string,
    sources: RagSource[],
    documentNames: string[],
  ): Promise<StudioDocument> {
    const data = await apiFetch<BackendNotebookNote>(`/notebooks/${encodeURIComponent(notebookId)}/notes`, {
      method: 'POST',
      body: JSON.stringify({
        question,
        answer,
        sources,
        document_names: documentNames,
      }),
    })

    return toStudioDocument(data)
  },
}
