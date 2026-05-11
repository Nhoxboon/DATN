import { useCallback, useEffect, useState } from 'react'
import type { ChatMessage, RagSource, StudioDocument } from '../types'
import { chatService } from '../services/chatService'

interface SaveNotePayload {
  assistantMessageId: string
  documentNames: string[]
}

function findQuestion(messages: ChatMessage[], assistantMessageId: string) {
  const index = messages.findIndex((message) => message.id === assistantMessageId)
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    if (messages[cursor]?.role === 'user') {
      return messages[cursor].content
    }
  }

  return ''
}

export function useChatManager(notebookId?: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isPending, setIsPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function loadConversation() {
      if (!notebookId) {
        setMessages([])
        return
      }

      try {
        setError(null)
        const nextMessages = await chatService.getConversation(notebookId)

        if (!cancelled) {
          setMessages(nextMessages)
        }
      } catch (err) {
        if (!cancelled) {
          setError((err as Error).message)
        }
      }
    }

    void loadConversation()

    return () => {
      cancelled = true
    }
  }, [notebookId])

  const sendMessage = useCallback(
    async (input: string, documentNames: string[]) => {
      if (!notebookId || !input.trim()) {
        return
      }

      setIsPending(true)
      setError(null)

      try {
        const nextMessages = await chatService.sendMessage(notebookId, input, documentNames)
        setMessages(nextMessages)
      } catch (err) {
        setError((err as Error).message)
      } finally {
        setIsPending(false)
      }
    },
    [notebookId],
  )

  const newChat = useCallback(async () => {
    if (!notebookId) {
      return
    }

    setIsPending(true)
    setError(null)

    try {
      const nextMessages = await chatService.newChat(notebookId)
      setMessages(nextMessages)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setIsPending(false)
    }
  }, [notebookId])

  const saveNote = useCallback(
    async ({ assistantMessageId, documentNames }: SaveNotePayload): Promise<StudioDocument | null> => {
      if (!notebookId) {
        return null
      }

      const assistantMessage = messages.find((message) => message.id === assistantMessageId)
      if (!assistantMessage || assistantMessage.role !== 'assistant') {
        return null
      }

      const question = findQuestion(messages, assistantMessageId)
      if (!question) {
        return null
      }

      const note = await chatService.saveNote(
        notebookId,
        question,
        assistantMessage.content,
        assistantMessage.sources || ([] as RagSource[]),
        documentNames.length
          ? documentNames
          : Array.from(new Set((assistantMessage.sources || []).map((source) => source.document))),
      )

      setMessages((current) =>
        current.map((message) =>
          message.id === assistantMessageId ? { ...message, saved: true } : message,
        ),
      )

      return note
    },
    [messages, notebookId],
  )

  return {
    messages,
    isPending,
    error,
    sendMessage,
    newChat,
    saveNote,
  }
}
