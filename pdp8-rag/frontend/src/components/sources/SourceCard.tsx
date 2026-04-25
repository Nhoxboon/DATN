import { FileText, Check } from 'lucide-react';

interface SourceCardProps {
  document: string;
  isSelected: boolean;
  onSelect: () => void;
  index: number;
}

export function SourceCard({ document, isSelected, onSelect, index }: SourceCardProps) {
  return (
    <button
      onClick={onSelect}
      className={`
        w-full px-3 py-3 rounded-lg text-left transition-all duration-200
        transform hover:scale-[1.02] active:scale-[0.98]
        animate-[slideInLeft_0.3s_ease-out]
        ${isSelected 
          ? 'bg-gradient-to-r from-blue-500 to-blue-600 text-white shadow-lg shadow-blue-500/25' 
          : 'bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-750 text-gray-900 dark:text-gray-100'
        }
      `}
      style={{
        animationDelay: `${index * 50}ms`,
        animationFillMode: 'both'
      }}
    >
      <div className="flex items-start gap-3">
        <div className={`
          flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center transition-colors
          ${isSelected 
            ? 'bg-white/20' 
            : 'bg-gray-100 dark:bg-gray-700'
          }
        `}>
          {isSelected ? (
            <Check className="w-4 h-4" />
          ) : (
            <FileText className="w-4 h-4 text-gray-600 dark:text-gray-400" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className={`
            font-medium text-sm mb-1 truncate
            ${isSelected ? 'text-white' : 'text-gray-900 dark:text-gray-100'}
          `}>
            {document}.pdf
          </div>
          <div className={`
            text-xs leading-relaxed truncate
            ${isSelected ? 'text-white/80' : 'text-gray-500 dark:text-gray-400'}
          `}>
            {document.replace(/_/g, ' ')}
          </div>
        </div>
      </div>
    </button>
  );
}