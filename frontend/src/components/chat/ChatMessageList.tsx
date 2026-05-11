import { BookmarkCheck, BookMarked } from 'lucide-react'
import type { ChatMessage } from '../../types'
import { useScrollToBottom } from '../../hooks/useScrollToBottom'

interface ChatMessageListProps {
  messages: ChatMessage[]
  onSaveNote?: (assistantMessageId: string) => void
  savingNoteId?: string | null
}

export function ChatMessageList({ messages, onSaveNote, savingNoteId }: ChatMessageListProps) {
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
            {isAssistant && Boolean(message.sources?.length) && (
              <div className="mt-3 flex flex-wrap gap-2">
                {message.sources?.slice(0, 4).map((source, index) => (
                  <span
                    key={`${message.id}-${source.document}-${index}`}
                    className="rounded-md bg-white px-2 py-1 text-[0.66rem] leading-none text-muted shadow-[inset_0_0_0_1px_rgba(171,179,183,0.16)]"
                  >
                    {source.document}
                    {source.page_range ? ` - ${source.page_range}` : ''}
                  </span>
                ))}
              </div>
            )}
            <div className={`mt-2 text-[0.72rem] uppercase tracking-[0.18em] ${isAssistant ? 'text-muted' : 'text-white/70'}`}>
              {message.timestamp}
            </div>
            {isAssistant && onSaveNote && (
              <button
                type="button"
                onClick={() => onSaveNote(message.id)}
                disabled={message.saved || savingNoteId === message.id}
                className="mt-3 inline-flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-[0.7rem] font-semibold text-primary transition hover:bg-white/80 disabled:cursor-default disabled:text-muted"
              >
                {message.saved ? <BookmarkCheck className="h-3.5 w-3.5" /> : <BookMarked className="h-3.5 w-3.5" />}
                {message.saved ? 'Đã lưu vào sổ ghi chú' : savingNoteId === message.id ? 'Đang lưu...' : 'Lưu vào sổ ghi chú'}
              </button>
            )}
          </article>
        )
      })}
    </div>
  )
}
