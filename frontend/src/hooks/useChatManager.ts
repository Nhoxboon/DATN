import { useCallback, useEffect, useState } from 'react'
import type { ChatMessage, RagSource, StudioDocument } from '../types'
import { chatService } from '../services/chatService'

const pendingStages = [
  'Sending question',
  'Checking selected sources',
  'Retrieving relevant chunks',
  'Running RAG reasoning',
  'Waiting for model response',
  'Formatting citations',
  'Still working',
]

interface SaveNotePayload {
  assistantMessageId: string
  documentNames: string[]
}

function localTimestamp() {
  return new Date().toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
  })
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

function answerModeFromStrategy(strategy?: string | null): ChatMessage['answerMode'] {
  if (!strategy) {
    return undefined
  }

  return strategy.toLowerCase().includes('multi') ? 'multihop' : 'singlehop'
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

      const now = Date.now()
      const localUserId = `local-user-${now}`
      const localAssistantId = `local-assistant-${now}`
      const localUserMessage: ChatMessage = {
        id: localUserId,
        role: 'user',
        content: input.trim(),
        timestamp: localTimestamp(),
      }
      const localAssistantMessage: ChatMessage = {
        id: localAssistantId,
        role: 'assistant',
        content: '',
        timestamp: localTimestamp(),
        pending: true,
        progressLabel: pendingStages[0],
      }

      setMessages((current) => [...current, localUserMessage, localAssistantMessage])

      let stageIndex = 0
      const stageTimer = window.setInterval(() => {
        stageIndex = Math.min(stageIndex + 1, pendingStages.length - 1)
        setMessages((current) =>
          current.map((message) =>
            message.id === localAssistantId
              ? { ...message, progressLabel: pendingStages[stageIndex] }
              : message,
          ),
        )
      }, 1400)

      let receivedStreamEvent = false

      try {
        await chatService.sendMessageStream(notebookId, input, documentNames, {
          onToken: (content) => {
            receivedStreamEvent = true
            setMessages((current) =>
              current.map((message) =>
                message.id === localAssistantId
                  ? {
                      ...message,
                      content: `${message.content}${content}`,
                      pending: false,
                      progressLabel: undefined,
                    }
                  : message,
              ),
            )
          },
          onMetadata: (metadata) => {
            receivedStreamEvent = true
            setMessages((current) =>
              current.map((message) =>
                message.id === localAssistantId
                  ? {
                      ...message,
                      sources: metadata.sources || [],
                      strategy: metadata.strategy,
                      strategyReasoning: metadata.strategy_reasoning,
                      answerMode: answerModeFromStrategy(metadata.strategy),
                    }
                  : message,
              ),
            )
          },
          onDone: (nextMessages) => {
            receivedStreamEvent = true
            setMessages(nextMessages)
          },
          onError: () => {
            receivedStreamEvent = true
          },
        })
      } catch (err) {
        let finalError = err
        if (!receivedStreamEvent) {
          try {
            const nextMessages = await chatService.sendMessage(notebookId, input, documentNames)
            setMessages(nextMessages)
            return
          } catch (fallbackErr) {
            finalError = fallbackErr
          }
        }

        const errorMessage = (finalError as Error).message
        setError(errorMessage)
        setMessages((current) =>
          current.map((message) =>
            message.id === localAssistantId
              ? {
                  ...message,
                  content: `Could not generate an answer: ${errorMessage}`,
                  pending: false,
                  error: true,
                  progressLabel: undefined,
                }
              : message,
          ),
        )
      } finally {
        window.clearInterval(stageTimer)
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
