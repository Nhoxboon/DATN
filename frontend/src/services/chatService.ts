import { initialChatMessages, notebookDetails } from '../data/mockData'
import type { ChatMessage } from '../types'
import { withDelay } from './api'

const conversationStore: Record<string, ChatMessage[]> = {}

function ensureConversation(notebookId: string) {
  if (!conversationStore[notebookId]) {
    conversationStore[notebookId] = structuredClone(initialChatMessages.default)
  }

  return conversationStore[notebookId]
}

export const chatService = {
  async getConversation(notebookId: string): Promise<ChatMessage[]> {
    return withDelay(structuredClone(ensureConversation(notebookId)))
  },

  async sendMessage(notebookId: string, input: string): Promise<ChatMessage[]> {
    const notebook = notebookDetails[notebookId]
    const conversation = ensureConversation(notebookId)

    conversation.push({
      id: crypto.randomUUID(),
      role: 'user',
      content: input,
      timestamp: 'Just now',
    })

    conversation.push({
      id: crypto.randomUUID(),
      role: 'assistant',
      timestamp: 'Just now',
      content: `For "${notebook?.title ?? 'this notebook'}", the strongest next move is to extract three claims from the selected sources, pressure-test them against counterexamples, and save the cleaned synthesis into Studio.`,
    })

    return withDelay(structuredClone(conversation), 420)
  },
}
