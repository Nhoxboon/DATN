import { marked } from 'marked';
import { useMemo } from 'react';
import { User, Bot, RefreshCw } from 'lucide-react';
import { Citation } from '../shared/Citation';
import { useTypewriter } from '../../hooks/useTypewriter';
import type { Message as MessageType } from '../../types';

marked.setOptions({
  breaks: true,
  gfm: true,
});

interface ContentPart {
  type: 'html' | 'citation';
  content?: string;
  number?: number;
  source?: any;
}

interface MessageProps {
  message: MessageType;
  index: number;
  skipTypewriter?: boolean;
}

export function Message({ message, index, skipTypewriter = false }: MessageProps) {
  // Use the typewriter hook ONLY for assistant messages that should animate
  const { displayedText, isTyping } = useTypewriter({
    text: message.role === 'assistant' && !skipTypewriter ? message.content : '',
    speed: 10, // Very fast typewriter (1ms per character)
    delay: 0,
  });

  // Determine what content to display
  const displayedContent = message.role === 'assistant' && !skipTypewriter 
    ? displayedText 
    : message.content;

  // Process content with citations
  const processedContent = useMemo(() => {
    if (!displayedContent) return [];

    // First parse the entire content as markdown
    let htmlContent = marked.parse(displayedContent) as string;

    // Remove wrapping paragraph tags if present
    htmlContent = htmlContent.trim();
    if (htmlContent.startsWith('<p>') && htmlContent.endsWith('</p>')) {
      const pCount = (htmlContent.match(/<p>/g) || []).length;
      if (pCount === 1) {
        htmlContent = htmlContent.slice(3, -4);
      }
    }

    // Now split by citation pattern and create parts
    const citationPattern = /\[(\d+(?:\s*,\s*\d+)*)\]/g;
    const parts: ContentPart[] = [];
    let lastIndex = 0;
    let match;

    while ((match = citationPattern.exec(htmlContent)) !== null) {
      // Add HTML before citation
      if (match.index > lastIndex) {
        parts.push({
          type: 'html',
          content: htmlContent.substring(lastIndex, match.index),
        });
      }

      // Add citation(s)
      const numbers = match[1].split(/\s*,\s*/).map(n => parseInt(n.trim()));
      numbers.forEach(num => {
        if (message.sources && message.sources[num - 1]) {
          parts.push({
            type: 'citation',
            number: num,
            source: message.sources[num - 1],
          });
        } else {
          parts.push({
            type: 'html',
            content: `[${num}]`,
          });
        }
      });

      lastIndex = match.index + match[0].length;
    }

    // Add remaining HTML
    if (lastIndex < htmlContent.length) {
      parts.push({
        type: 'html',
        content: htmlContent.substring(lastIndex),
      });
    }

    // If no parts were created, return the whole content as HTML
    if (parts.length === 0) {
      parts.push({
        type: 'html',
        content: htmlContent,
      });
    }

    return parts;
  }, [displayedContent, message.sources]);

  if (message.role === 'user') {
    return (
      <div 
        className="flex justify-end animate-[slideInRight_0.3s_ease-out]"
        style={{ animationDelay: `${index * 50}ms`, animationFillMode: 'both' }}
      >
        <div className="flex items-start gap-3 max-w-[85%]">
          <div className="flex-1 bg-gradient-to-br from-blue-500 to-blue-600 text-white px-4 py-3 rounded-2xl rounded-tr-sm shadow-lg shadow-blue-500/25">
            <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">
              {message.content}
            </p>
          </div>
          <div className="flex-shrink-0 w-8 h-8 bg-gradient-to-br from-blue-500 to-cyan-600 rounded-full flex items-center justify-center shadow-lg">
            <User className="w-4 h-4 text-white" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div 
      className="flex justify-start animate-[slideInLeft_0.3s_ease-out]"
      style={{ animationDelay: `${index * 50}ms`, animationFillMode: 'both' }}
    >
      <div className="flex items-start gap-3 max-w-[95%]">
        <div className="flex-shrink-0 w-8 h-8 bg-gradient-to-br from-gray-700 to-gray-800 dark:from-gray-600 dark:to-gray-700 rounded-full flex items-center justify-center shadow-lg">
          <Bot className="w-4 h-4 text-white" />
        </div>
        <div className="flex-1">
          {/* Strategy Badge */}
          {message.strategy && (
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-300 rounded-full text-xs font-medium mb-2">
              <RefreshCw className="w-3 h-3" />
              {message.strategy === 'multi-hop' ? 'Multi-hop' : 'Single-hop'}
            </div>
          )}

          {/* Message Content */}
          <div className="bg-gray-100 dark:bg-gray-800 px-4 py-3 rounded-2xl rounded-tl-sm shadow-sm">
            <div className="text-sm leading-relaxed text-gray-900 dark:text-gray-100 prose prose-sm dark:prose-invert max-w-none [&_strong]:font-semibold [&_strong]:text-gray-900 [&_strong]:dark:text-white [&_p]:mb-3 [&_p:last-child]:mb-0 [&_ul]:ml-4 [&_ul]:mb-3 [&_ol]:ml-4 [&_ol]:mb-3 [&_li]:mb-1">
              {processedContent.map((part, partIndex) => {
                if (part.type === 'citation') {
                  return (
                    <Citation
                      key={`citation-${partIndex}`}
                      source={part.source}
                      number={part.number!}
                    />
                  );
                } else {
                  return (
                    <span
                      key={`html-${partIndex}`}
                      dangerouslySetInnerHTML={{ __html: part.content! }}
                    />
                  );
                }
              })}
              {isTyping && (
                <span className="inline-block w-1 h-4 bg-blue-500 ml-0.5 animate-pulse" />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}