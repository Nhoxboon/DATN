import { useScrollToBottom } from '../../hooks/useScrollToBottom';
import { Message } from './Message';
import { StreamingIndicator } from './StreamingIndicator';
import type { Message as MessageType } from '../../types';

interface ChatMessagesProps {
  messages: MessageType[];
  streaming: boolean;
  sessionId: string; // NEW: For proper component key management
}

export function ChatMessages({ messages, streaming, sessionId }: ChatMessagesProps) {
  const messagesEndRef = useScrollToBottom<HTMLDivElement>({
    dependencies: [messages, streaming, sessionId], // UPDATED: Include sessionId
    behavior: 'smooth',
  });

  return (
    <div
      ref={messagesEndRef}
      className="chat-messages h-full overflow-y-auto overflow-x-hidden px-4 sm:px-6 lg:px-8 py-6"
      key={sessionId} // NEW: Force re-render on session change
    >
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Welcome Message */}
        {messages.length === 0 && !streaming && (
          <div className="animate-[fadeIn_0.5s_ease-out]">
            <div className="dark:bg-gray-900 px-6 py-6 rounded-lg dark:text-gray-300 bg-white text-gray-800 shadow-md">
              <p className="mb-4">👋 Welcome! I can help you understand Vietnam's Electricity Master Plan VIII (PDP8).</p>
              <p className="mb-4">Ask me about:</p>
              <ul className="ml-6 space-y-2">
                <li>LNG power projects and development timeline</li>
                <li>Renewable energy targets and capacity expansion</li>
                <li>Grid infrastructure and transmission planning</li>
                <li>Coal phase-out and energy transition strategies</li>
                <li>Investment requirements and financial mechanisms</li>
              </ul>
            </div>
          </div>
        )}

        {/* Messages */}
        {messages.map((message, index) => {
          // Only apply typewriter to the LAST assistant message AND only when actively streaming
          const shouldAnimate = 
            message.role === 'assistant' && 
            index === messages.length - 1 &&
            streaming;
          
          return (
            <Message
              key={`${sessionId}-msg-${index}`}
              message={message}
              index={index}
              skipTypewriter={!shouldAnimate}
            />
          );
        })}

        {/* Streaming Indicator - Only for active streaming in THIS session */}
        {streaming && <StreamingIndicator key={`${sessionId}-streaming`} />}
      </div>
    </div>
  );
}