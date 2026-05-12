import { Bot, Bookmark, BookmarkCheck, Check, Copy, UserRound } from 'lucide-react'
import { createPortal } from 'react-dom'
import { useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { ChatMessage, RagSource } from '../../types'
import { useScrollToBottom } from '../../hooks/useScrollToBottom'

interface ChatMessageListProps {
  messages: ChatMessage[]
  intro?: ReactNode
  onSaveNote?: (assistantMessageId: string) => void
  savingNoteId?: string | null
}

const citationPattern = /\[(\d+(?:\s*,\s*\d+)*)\]/g

function sourceSummary(source: RagSource) {
  const similarity =
    typeof source.similarity === 'number' && Number.isFinite(source.similarity)
      ? ` - ${(source.similarity * 100).toFixed(1)}% relevance`
      : ''

  return `${source.document || 'Unknown document'}${source.page_range ? ` - pages ${source.page_range}` : ''}${similarity}`
}

function CitationMarker({ number, source }: { number: number; source: RagSource }) {
  const triggerRef = useRef<HTMLElement | null>(null)
  const [popup, setPopup] = useState<{ left: number; top: number; placement: 'above' | 'below' } | null>(null)

  const showPopup = () => {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) {
      return
    }

    const popupWidth = Math.min(380, window.innerWidth - 32)
    const left = Math.min(Math.max(rect.left + rect.width / 2, popupWidth / 2 + 16), window.innerWidth - popupWidth / 2 - 16)
    const placement = rect.top > 260 ? 'above' : 'below'
    const top = placement === 'above' ? rect.top - 10 : rect.bottom + 10

    setPopup({ left, top, placement })
  }

  const hidePopup = () => {
    setPopup(null)
  }

  const tooltip = popup
    ? createPortal(
        <div
          className="pointer-events-none fixed z-[100] max-h-[360px] w-[min(380px,calc(100vw-32px))] overflow-y-auto rounded-xl border border-black/10 bg-white text-left text-[0.76rem] leading-5 text-ink shadow-[0_18px_60px_rgba(43,52,55,0.24)]"
          style={{
            left: popup.left,
            top: popup.top,
            transform: popup.placement === 'above' ? 'translate(-50%, -100%)' : 'translate(-50%, 0)',
          }}
        >
          <div className="border-b border-black/8 bg-surface-low px-4 py-3">
            <div className="font-semibold text-primary">{source.document || 'Unknown document'}</div>
            <div className="mt-1 text-[0.68rem] text-muted">
              {source.page_range ? `Pages ${source.page_range}` : 'Pages unknown'}
              {typeof source.similarity === 'number' && Number.isFinite(source.similarity)
                ? ` - ${(source.similarity * 100).toFixed(1)}% relevance`
                : ''}
            </div>
            {source.has_visual && (
              <div className="mt-2 inline-flex rounded-full bg-[rgba(0,91,192,0.1)] px-2 py-0.5 text-[0.62rem] font-semibold text-primary">
                Visual extraction
              </div>
            )}
          </div>
          <div className="whitespace-pre-wrap px-4 py-3 text-[0.74rem] leading-6 text-ink">
            {source.image_url && (
              <img
                src={source.image_url}
                alt={`${source.document || 'Document'} visual source`}
                className="mb-3 max-h-48 w-full rounded-lg bg-surface-low object-contain"
              />
            )}
            {source.content || 'No source text available.'}
          </div>
        </div>,
        document.body,
      )
    : null

  return (
    <>
      <sup
        ref={triggerRef}
        className="mx-0.5 inline-block cursor-pointer align-baseline"
        onMouseEnter={showPopup}
        onMouseLeave={hidePopup}
        title={sourceSummary(source)}
      >
        <span className="rounded px-1 py-0.5 text-[0.9em] font-semibold leading-none text-primary transition hover:bg-[rgba(0,91,192,0.1)]">
          [{number}]
        </span>
      </sup>
      {tooltip}
    </>
  )
}

function renderMessageContent(message: ChatMessage) {
  if (message.pending) {
    return (
      <div className="flex items-center gap-3">
        <span className="inline-flex items-center gap-1">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.2s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.1s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary" />
        </span>
        <span className="text-xs font-semibold text-muted">{message.progressLabel || 'Responding'}</span>
      </div>
    )
  }

  const parts: ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null

  citationPattern.lastIndex = 0
  while ((match = citationPattern.exec(message.content)) !== null) {
    if (match.index > lastIndex) {
      parts.push(
        <span key={`text-${lastIndex}`} className="whitespace-pre-wrap">
          {message.content.slice(lastIndex, match.index)}
        </span>,
      )
    }

    const numbers = match[1].split(/\s*,\s*/).map((value) => Number.parseInt(value, 10))
    numbers.forEach((number, index) => {
      const source = message.sources?.[number - 1]
      parts.push(
        source ? (
          <CitationMarker key={`citation-${match?.index}-${number}-${index}`} number={number} source={source} />
        ) : (
          <span key={`missing-citation-${match?.index}-${number}-${index}`}>[{number}]</span>
        ),
      )
    })

    lastIndex = match.index + match[0].length
  }

  if (lastIndex < message.content.length) {
    parts.push(
      <span key={`text-${lastIndex}`} className="whitespace-pre-wrap">
        {message.content.slice(lastIndex)}
      </span>,
    )
  }

  return parts.length ? parts : <span className="whitespace-pre-wrap">{message.content}</span>
}

export function ChatMessageList({ messages, intro, onSaveNote, savingNoteId }: ChatMessageListProps) {
  const scrollRef = useScrollToBottom(messages)
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null)

  const copyAnswer = async (message: ChatMessage) => {
    await navigator.clipboard.writeText(message.content)
    setCopiedMessageId(message.id)
    window.setTimeout(() => {
      setCopiedMessageId((current) => (current === message.id ? null : current))
    }, 1400)
  }

  return (
    <div ref={scrollRef} className="h-full min-h-0 space-y-4 overflow-y-auto pr-1">
      {intro}
      {messages.map((message) => {
        const isAssistant = message.role === 'assistant'
        const canUseAssistantActions = isAssistant && !message.pending && !message.error

        return (
          <div
            key={message.id}
            className={`flex items-start gap-3 ${isAssistant ? 'justify-start' : 'justify-end'}`}
          >
            {isAssistant && (
              <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white text-primary shadow-[inset_0_0_0_1px_rgba(171,179,183,0.28)]">
                <Bot className="h-4 w-4" />
              </div>
            )}
            <article
              className={`max-w-[92%] rounded-[24px] px-4 py-3.5 text-sm leading-7 shadow-paper ${
                isAssistant
                  ? message.error
                    ? 'bg-red-50 text-red-900'
                    : 'bg-surface-low text-ink'
                  : 'bg-gradient-to-br from-primary to-primary-deep text-white'
              }`}
            >
              {isAssistant && message.answerMode && !message.pending && (
                <div className="mb-2 text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-primary">
                  [{message.answerMode}]
                </div>
              )}
              <div>{renderMessageContent(message)}</div>
              {isAssistant && !message.pending && Boolean(message.sources?.length) && (
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
              {canUseAssistantActions && (
                <div className="mt-3 flex items-center gap-2">
                  {onSaveNote && (
                    <button
                      type="button"
                      onClick={() => onSaveNote(message.id)}
                      disabled={message.saved || savingNoteId === message.id}
                      className="inline-flex items-center gap-2 rounded-xl border border-outline/50 bg-white px-3.5 py-2 text-[0.7rem] font-semibold text-primary transition hover:bg-white/80 disabled:cursor-default disabled:text-primary/55"
                    >
                      {message.saved ? <BookmarkCheck className="h-3.5 w-3.5" /> : <Bookmark className="h-3.5 w-3.5" />}
                      {message.saved ? 'Saved to note' : savingNoteId === message.id ? 'Saving...' : 'Save to note'}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      void copyAnswer(message)
                    }}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-xl border border-outline/50 bg-white text-primary transition hover:bg-white/80"
                    aria-label="Copy answer"
                    title="Copy answer"
                  >
                    {copiedMessageId === message.id ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  </button>
                </div>
              )}
            </article>
            {!isAssistant && (
              <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                <UserRound className="h-4 w-4" />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}