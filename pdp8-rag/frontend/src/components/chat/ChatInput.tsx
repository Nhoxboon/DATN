import { useState, FormEvent, KeyboardEvent, ChangeEvent, useRef, useEffect } from 'react';
import { Send, Loader2 } from 'lucide-react';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [message, setMessage] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px';
    }
  }, [message]);

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (message.trim() && !disabled) {
      onSend(message.trim());
      setMessage('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as any);
    }
  };

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setMessage(e.target.value);
  };

  return (
    <div className="border-t border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 backdrop-blur-xl transition-colors duration-300">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <form onSubmit={handleSubmit} className="relative">
          <div className="relative flex items-end gap-2">
            <div className="flex-1 relative">
              <textarea
                ref={textareaRef}
                className="w-full min-h-[52px] max-h-[200px] resize-none px-4 py-3 pr-12 bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 leading-6 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
                value={message}
                onChange={handleChange}
                onKeyDown={handleKeyDown}
                placeholder="Ask about LNG projects, grid development, renewable targets..."
                disabled={disabled}
                rows={1}
              />
              
              {/* Character count hint */}
              {message.length > 0 && (
                <div className="absolute bottom-2 right-2 text-xs text-gray-400 dark:text-gray-500">
                  {message.length}
                </div>
              )}
            </div>

            <button
              type="submit"
              className={`
                flex-shrink-0 flex items-center justify-center w-12 h-12 rounded-xl
                transition-all duration-200 transform
                ${message.trim() && !disabled
                  ? 'bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 hover:scale-105 active:scale-95'
                  : 'bg-gray-200 dark:bg-gray-800 text-gray-400 dark:text-gray-600 cursor-not-allowed'
                }
              `}
              disabled={disabled || !message.trim()}
            >
              {disabled ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Send className="w-5 h-5" />
              )}
            </button>
          </div>

          {/* Hint text */}
          <div className="mt-2 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
            <span>Press Enter to send, Shift + Enter for new line</span>
            {disabled && (
              <span className="flex items-center gap-1 text-blue-500">
                <Loader2 className="w-3 h-3 animate-spin" />
                Generating response...
              </span>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}