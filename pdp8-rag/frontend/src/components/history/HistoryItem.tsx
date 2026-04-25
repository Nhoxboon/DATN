import { MessageCircle } from 'lucide-react';
import type { HistoryItem } from '../../types';

interface HistoryItemProps {
  item: HistoryItem;
  onSelect: () => void;
  index: number;
}

export function HistoryItem({ item, onSelect, index }: HistoryItemProps) {
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
    <button
      onClick={onSelect}
      className="w-full px-3 py-3 rounded-lg text-left transition-all duration-200 transform hover:scale-[1.02] active:scale-[0.98] bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-750 animate-[slideInRight_0.3s_ease-out] group"
      style={{
        animationDelay: `${index * 50}ms`,
        animationFillMode: 'both'
      }}
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-gray-100 dark:bg-gray-700 flex items-center justify-center group-hover:bg-blue-100 dark:group-hover:bg-blue-900/30 transition-colors">
          <MessageCircle className="w-4 h-4 text-gray-600 dark:text-gray-400 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2 mb-1">
            {item.preview}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">
            {formatTimestamp(item.timestamp)}
          </div>
        </div>
      </div>
    </button>
  );
}