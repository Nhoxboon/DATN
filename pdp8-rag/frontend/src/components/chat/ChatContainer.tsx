import { ChatMessages } from './ChatMessages';
import { ChatInput } from './ChatInput';
import type { Message } from '../../types';

interface ChatContainerProps {
  messages: Message[];
  streaming: boolean;
  onSendMessage: (message: string) => void;
  sessionId: string;
}

export function ChatContainer({ 
  messages, 
  streaming, 
  onSendMessage,
  sessionId 
}: ChatContainerProps) {
  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-950 transition-colors duration-300">
      {/* Messages Area - Flex-1 with overflow */}
      <div className="flex-1 min-h-0">
        <ChatMessages 
          messages={messages} 
          streaming={streaming}
          sessionId={sessionId}
        />
      </div>

      {/* Input Area - Always shown, can continue any conversation */}
      <div className="flex-shrink-0">
        <ChatInput onSend={onSendMessage} disabled={streaming} />
      </div>
    </div>
  );
}