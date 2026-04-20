import { useEffect, useState, useTransition } from 'react'
import type { ChatMessage } from '../types'
import { chatService } from '../services/chatService'

export function useChatManager(notebookId?: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isPending, startTransition] = useTransition()

  useEffect(() => {
    let cancelled = false

    async function loadConversation() {
      if (!notebookId) {
        setMessages([])
        return
      }

      const nextMessages = await chatService.getConversation(notebookId)

      if (!cancelled) {
        setMessages(nextMessages)
      }
    }

    void loadConversation()

    return () => {
      cancelled = true
    }
  }, [notebookId])

  const sendMessage = (input: string) => {
    if (!notebookId || !input.trim()) {
      return
    }

    startTransition(async () => {
      const nextMessages = await chatService.sendMessage(notebookId, input)
      setMessages(nextMessages)
    })
  }

  return {
    messages,
    isPending,
    sendMessage,
  }
}
