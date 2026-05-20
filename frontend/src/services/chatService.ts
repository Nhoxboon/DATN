import type {
  BackendChatCurrent,
  BackendChatMessage,
  BackendChatSendResponse,
  BackendNotebookNote,
  ChatMessage,
  RagSource,
  StudioDocument,
} from '../types'
import { apiFetch, apiRequest } from './api'

interface ChatStreamMetadata {
  sources?: RagSource[]
  strategy?: string | null
  strategy_reasoning?: string | null
}

interface ChatStreamDone extends ChatStreamMetadata {
  session_id: string
  messages: BackendChatMessage[]
}

interface ChatStreamHandlers {
  onToken: (content: string) => void
  onMetadata: (metadata: ChatStreamMetadata) => void
  onDone: (messages: ChatMessage[]) => void
  onError?: (message: string) => void
}

type ChatStreamEvent =
  | { type: 'token'; content?: string }
  | ({ type: 'metadata' } & ChatStreamMetadata)
  | ({ type: 'done' } & ChatStreamDone)
  | { type: 'error'; message?: string }

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

function answerModeFromStrategy(strategy?: string | null): ChatMessage['answerMode'] {
  if (!strategy) {
    return undefined
  }

  return strategy.toLowerCase().includes('multi') ? 'multihop' : 'singlehop'
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

function withResponseStrategy(messages: ChatMessage[], data: BackendChatSendResponse) {
  const assistantIndex = messages.findLastIndex((message) => message.role === 'assistant')
  if (assistantIndex === -1 || !data.strategy) {
    return messages
  }

  return messages.map((message, index) =>
    index === assistantIndex
      ? {
          ...message,
          strategy: data.strategy,
          strategyReasoning: data.strategy_reasoning,
          answerMode: answerModeFromStrategy(data.strategy),
        }
      : message,
  )
}

function withStreamStrategy(messages: ChatMessage[], data: ChatStreamMetadata) {
  const assistantIndex = messages.findLastIndex((message) => message.role === 'assistant')
  if (assistantIndex === -1 || !data.strategy) {
    return messages
  }

  return messages.map((message, index) =>
    index === assistantIndex
      ? {
          ...message,
          strategy: data.strategy,
          strategyReasoning: data.strategy_reasoning,
          answerMode: answerModeFromStrategy(data.strategy),
        }
      : message,
  )
}

function handleStreamEvent(event: ChatStreamEvent, handlers: ChatStreamHandlers) {
  if (event.type === 'token') {
    handlers.onToken(event.content || '')
    return
  }

  if (event.type === 'metadata') {
    handlers.onMetadata({
      sources: event.sources || [],
      strategy: event.strategy,
      strategy_reasoning: event.strategy_reasoning,
    })
    return
  }

  if (event.type === 'done') {
    handlers.onDone(withStreamStrategy(toMessages(event.messages), event))
    return
  }

  if (event.type === 'error') {
    const message = event.message || 'Streaming response failed'
    handlers.onError?.(message)
    throw new Error(message)
  }
}

async function readNdjsonStream(response: Response, handlers: ChatStreamHandlers) {
  if (!response.body) {
    throw new Error('Streaming is not supported by this browser.')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const processLine = (line: string) => {
    const trimmed = line.trim()
    if (!trimmed) {
      return
    }
    handleStreamEvent(JSON.parse(trimmed) as ChatStreamEvent, handlers)
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) {
      break
    }

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split(/\r?\n/)
    buffer = lines.pop() || ''
    lines.forEach(processLine)
  }

  buffer += decoder.decode()
  processLine(buffer)
}

function toStudioDocument(note: BackendNotebookNote): StudioDocument {
  const excerpt = note.answer.replace(/\s+/g, ' ').slice(0, 150)

  return {
    id: note.id,
    itemType: 'note',
    icon: 'description',
    title: note.question,
    excerpt: excerpt ? `${excerpt}${note.answer.length > 150 ? '...' : ''}` : 'Saved AI answer',
    updatedAt: 'Saved just now',
    sortTimestamp: new Date().toISOString(),
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

    return withResponseStrategy(toMessages(data.messages), data)
  },

  async sendMessageStream(
    notebookId: string,
    input: string,
    documentNames: string[],
    handlers: ChatStreamHandlers,
  ): Promise<void> {
    const response = await apiRequest(
      `/notebooks/${encodeURIComponent(notebookId)}/chat/messages/stream`,
      {
        method: 'POST',
        body: JSON.stringify({
          message: input,
          document_names: documentNames,
        }),
      },
    )

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || `Request failed with status ${response.status}`)
    }

    await readNdjsonStream(response, handlers)
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
