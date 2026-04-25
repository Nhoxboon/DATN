import { Clock, Trash2, Loader2 } from 'lucide-react';
import type { ChatSession } from '../../types';

interface SessionItemProps {
  session: ChatSession;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
  index: number;
}

function SessionItem({ session, isActive, onSelect, onDelete, index }: SessionItemProps) {
  const formatTimestamp = (date: string) => {
    const now = new Date();
    const diff = now.getTime() - new Date(date).getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return 'Just now';
    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    if (days < 7) return `${days}d ago`;

    return new Date(date).toLocaleDateString();
  };

  return (
    <div
      className={`
        group relative w-full px-3 py-3 rounded-lg transition-all duration-200 
        animate-[slideInRight_0.3s_ease-out]
        ${isActive
          ? 'bg-gradient-to-r from-blue-500 to-blue-600 text-white shadow-lg shadow-blue-500/25'
          : 'bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-750'
        }
      `}
      style={{
        animationDelay: `${index * 30}ms`,
        animationFillMode: 'both'
      }}
    >
      <button
        onClick={onSelect}
        className="w-full text-left"
      >
        <div className="flex items-start gap-3">
          <div className={`
            flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center transition-colors
            ${isActive
              ? 'bg-white/20'
              : 'bg-gray-100 dark:bg-gray-700'
            }
          `}>
            {session.streaming ? (
              <Loader2 className={`
                w-4 h-4 animate-spin
                ${isActive ? 'text-white' : 'text-blue-600 dark:text-blue-400'}
              `} />
            ) : (
              <Clock className={`
                w-4 h-4
                ${isActive ? 'text-white' : 'text-gray-600 dark:text-gray-400'}
              `} />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className={`
              text-sm font-medium line-clamp-2 mb-1
              ${isActive ? 'text-white' : 'text-gray-900 dark:text-gray-100'}
            `}>
              {session.preview}
              {session.streaming && (
                <span className={`ml-2 text-xs ${isActive ? 'text-white/80' : 'text-blue-600 dark:text-blue-400'}`}>
                  (processing...)
                </span>
              )}
            </div>
            <div className={`
              text-xs flex items-center gap-2
              ${isActive ? 'text-white/80' : 'text-gray-500 dark:text-gray-400'}
            `}>
              <span>{formatTimestamp(session.updatedAt)}</span>
              {session.messages.length > 0 && (
                <span>• {Math.ceil(session.messages.length / 2)} msgs</span>
              )}
            </div>
          </div>
        </div>
      </button>

      {/* Delete button - only show on hover and if not active streaming */}
      {!session.streaming && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className={`
            absolute top-2 right-2 p-1.5 rounded-lg opacity-0 group-hover:opacity-100
            transition-all duration-200 transform hover:scale-110 active:scale-95
            ${isActive
              ? 'bg-white/20 hover:bg-white/30 text-white'
              : 'bg-gray-100 dark:bg-gray-700 hover:bg-red-50 dark:hover:bg-red-900/20 text-gray-500 hover:text-red-600 dark:hover:text-red-400'
            }
          `}
          title="Delete conversation"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}

interface HistoryPanelProps {
  sessions: ChatSession[];
  activeSessionId: string;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
}

export function HistoryPanel({ 
  sessions,
  activeSessionId,
  onSelectSession,
  onDeleteSession,
}: HistoryPanelProps) {
  return (
    <aside className="h-full flex flex-col bg-gray-50 dark:bg-gray-900 transition-colors duration-300">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-4 border-b border-gray-200 dark:border-gray-800">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-gray-600 dark:text-gray-400" />
          <h2 className="font-semibold text-sm text-gray-900 dark:text-gray-100">
            All Chats
          </h2>
        </div>
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {sessions.length}
        </span>
      </div>

      {/* Sessions List */}
      <div 
        className="flex-1 overflow-y-auto px-2 py-2 space-y-1"
        style={{
          scrollbarWidth: 'none',
          msOverflowStyle: 'none',
          WebkitOverflowScrolling: 'touch'
        }}
      >
        {sessions.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-gray-200 dark:bg-gray-800 flex items-center justify-center">
              <Clock className="w-6 h-6 text-gray-400 dark:text-gray-600" />
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              No conversations yet
            </p>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
              Start a new chat to begin
            </p>
          </div>
        ) : (
          sessions.map((session, index) => (
            <SessionItem
              key={session.id}
              session={session}
              isActive={session.id === activeSessionId}
              onSelect={() => onSelectSession(session.id)}
              onDelete={() => onDeleteSession(session.id)}
              index={index}
            />
          ))
        )}
      </div>

      {/* Footer */}
      {sessions.length > 0 && (
        <div className="px-4 py-3 border-t border-gray-200 dark:border-gray-800">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {sessions.filter(s => s.streaming).length > 0 && (
              <span className="text-blue-600 dark:text-blue-400">
                {sessions.filter(s => s.streaming).length} processing
                {sessions.length > sessions.filter(s => s.streaming).length && ' • '}
              </span>
            )}
            {sessions.length} total
          </p>
        </div>
      )}
      
      {/* Webkit scrollbar hide */}
      <style>{`
        .flex-1.overflow-y-auto::-webkit-scrollbar {
          display: none;
        }
      `}</style>
    </aside>
  );
}