import type { ChatMessage } from '../../types'
import { useScrollToBottom } from '../../hooks/useScrollToBottom'

export function ChatMessageList({ messages }: { messages: ChatMessage[] }) {
  const scrollRef = useScrollToBottom(messages)

  return (
    <div ref={scrollRef} className="max-h-[320px] space-y-4 overflow-y-auto pr-1">
      {messages.map((message) => {
        const isAssistant = message.role === 'assistant'

        return (
          <article
            key={message.id}
            className={`max-w-[92%] rounded-[24px] px-4 py-3.5 text-sm leading-7 shadow-paper ${
              isAssistant
                ? 'bg-surface-low text-ink'
                : 'ml-auto bg-gradient-to-br from-primary to-primary-deep text-white'
            }`}
          >
            <div>{message.content}</div>
            <div className={`mt-2 text-[0.72rem] uppercase tracking-[0.18em] ${isAssistant ? 'text-muted' : 'text-white/70'}`}>
              {message.timestamp}
            </div>
          </article>
        )
      })}
    </div>
  )
}
