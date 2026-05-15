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
const boldPattern = /\*\*(.+?)\*\*/g

function renderBoldText(text: string, keyPrefix: string) {
  const parts: ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null

  boldPattern.lastIndex = 0
  while ((match = boldPattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index))
    }
    parts.push(
      <strong key={`${keyPrefix}-bold-${match.index}`} className="font-semibold">
        {match[1]}
      </strong>,
    )
    lastIndex = match.index + match[0].length
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }

  return parts.length ? parts : text
}

function renderInlineContent(text: string, message: ChatMessage, keyPrefix: string) {
  const parts: ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null

  citationPattern.lastIndex = 0
  while ((match = citationPattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(...renderBoldText(text.slice(lastIndex, match.index), `${keyPrefix}-text-${lastIndex}`))
    }

    const numbers = match[1].split(/\s*,\s*/).map((value) => Number.parseInt(value, 10))
    numbers.forEach((number, index) => {
      const source = message.sources?.[number - 1]
      parts.push(
        source ? (
          <CitationMarker key={`${keyPrefix}-citation-${match?.index}-${number}-${index}`} number={number} source={source} />
        ) : (
          <span key={`${keyPrefix}-missing-citation-${match?.index}-${number}-${index}`}>[{number}]</span>
        ),
      )
    })

    lastIndex = match.index + match[0].length
  }

  if (lastIndex < text.length) {
    parts.push(...renderBoldText(text.slice(lastIndex), `${keyPrefix}-text-${lastIndex}`))
  }

  return parts.length ? parts : renderBoldText(text, `${keyPrefix}-text`)
}

function isUnorderedListItem(line: string) {
  return /^\s*[-*]\s+/.test(line)
}

function isOrderedListItem(line: string) {
  return /^\s*\d+\.\s+/.test(line)
}

function listItemText(line: string) {
  return line.replace(/^\s*(?:[-*]|\d+\.)\s+/, '')
}

function splitTableRow(line: string) {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim())
}

function isTableSeparator(line: string) {
  const cells = splitTableRow(line)
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell))
}

function isTableStart(lines: string[], index: number) {
  return lines[index]?.includes('|') && Boolean(lines[index + 1]) && isTableSeparator(lines[index + 1])
}

function sourceSummary(source: RagSource) {
  return `${source.document || 'Unknown document'}${source.page_range ? ` - pages ${source.page_range}` : ''}${formatRelevance(source)}`
}

function formatRelevance(source: RagSource) {
  return typeof source.similarity === 'number' && Number.isFinite(source.similarity) && source.similarity > 0
    ? ` - ${(source.similarity * 100).toFixed(1)}% relevance`
    : ''
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
              {formatRelevance(source)}
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

  const lines = message.content.split(/\r?\n/)
  const blocks: ReactNode[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]

    if (!line.trim()) {
      index += 1
      continue
    }

    const heading = /^(#{1,6})\s+(.+)$/.exec(line)
    if (heading) {
      blocks.push(
        <h3 key={`heading-${index}`} className="mt-3 first:mt-0 text-[0.98rem] font-semibold leading-6 text-ink">
          {renderInlineContent(heading[2], message, `heading-${index}`)}
        </h3>,
      )
      index += 1
      continue
    }

    if (isUnorderedListItem(line) || isOrderedListItem(line)) {
      const ordered = isOrderedListItem(line)
      const items: string[] = []
      while (index < lines.length && (ordered ? isOrderedListItem(lines[index]) : isUnorderedListItem(lines[index]))) {
        items.push(listItemText(lines[index]))
        index += 1
      }

      const ListTag = ordered ? 'ol' : 'ul'
      blocks.push(
        <ListTag
          key={`list-${index}`}
          className={`my-2 space-y-1 pl-5 ${ordered ? 'list-decimal' : 'list-disc'}`}
        >
          {items.map((item, itemIndex) => (
            <li key={`list-${index}-${itemIndex}`} className="pl-1 leading-7">
              {renderInlineContent(item, message, `list-${index}-${itemIndex}`)}
            </li>
          ))}
        </ListTag>,
      )
      continue
    }

    if (isTableStart(lines, index)) {
      const header = splitTableRow(lines[index])
      index += 2
      const rows: string[][] = []
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        rows.push(splitTableRow(lines[index]))
        index += 1
      }

      blocks.push(
        <div key={`table-${index}`} className="my-3 max-w-full overflow-x-auto rounded-lg border border-black/8 bg-white">
          <table className="min-w-full border-collapse text-left text-[0.76rem] leading-5">
            <thead className="bg-surface-low text-ink">
              <tr>
                {header.map((cell, cellIndex) => (
                  <th key={`table-${index}-head-${cellIndex}`} className="border-b border-black/8 px-3 py-2 font-semibold">
                    {renderInlineContent(cell, message, `table-${index}-head-${cellIndex}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={`table-${index}-row-${rowIndex}`} className="border-b border-black/5 last:border-b-0">
                  {row.map((cell, cellIndex) => (
                    <td key={`table-${index}-row-${rowIndex}-${cellIndex}`} className="px-3 py-2 align-top">
                      {renderInlineContent(cell, message, `table-${index}-row-${rowIndex}-${cellIndex}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }

    const paragraphLines = [line]
    index += 1
    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^(#{1,6})\s+/.test(lines[index]) &&
      !isUnorderedListItem(lines[index]) &&
      !isOrderedListItem(lines[index]) &&
      !isTableStart(lines, index)
    ) {
      paragraphLines.push(lines[index])
      index += 1
    }

    blocks.push(
      <p key={`paragraph-${index}`} className="my-2 first:mt-0 last:mb-0 whitespace-pre-wrap leading-7">
        {renderInlineContent(paragraphLines.join('\n'), message, `paragraph-${index}`)}
      </p>,
    )
  }

  return blocks.length ? blocks : <span className="whitespace-pre-wrap">{message.content}</span>
}

export function RichAnswerContent({ content, sources }: { content: string; sources?: RagSource[] }) {
  return (
    <>
      {renderMessageContent({
        id: 'rich-answer',
        role: 'assistant',
        content,
        timestamp: '',
        sources,
      })}
    </>
  )
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
