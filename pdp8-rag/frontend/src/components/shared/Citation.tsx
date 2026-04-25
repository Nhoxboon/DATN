// src/components/shared/Citation.tsx
import { useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import ReactMarkdown from 'react-markdown';
import { usePortal } from '../../hooks/usePortal';
import { usePopupPosition } from '../../hooks/usePopupPosition';

interface CitationSource {
  document?: string;
  page_range: string;
  similarity: number;
  content: string;
}

interface CitationProps {
  source: CitationSource;
  number: number;
}

export function Citation({ source, number }: CitationProps) {
  const [showPopup, setShowPopup] = useState(false);
  const citationRef = useRef<HTMLElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const hideTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const portalContainer = usePortal('citation-portal');

  const position = usePopupPosition({
    isVisible: showPopup,
    triggerRef: citationRef,
    popupRef: popupRef,
    offset: 12,
    padding: 20,
  });

  const handleMouseEnter = () => {
    if (hideTimeoutRef.current) {
      clearTimeout(hideTimeoutRef.current);
      hideTimeoutRef.current = null;
    }

    setShowPopup(true);
  };

  const handleMouseLeave = () => {

    hideTimeoutRef.current = setTimeout(() => {
      setShowPopup(false);
    }, 100);
  };

  const popupContent = showPopup && portalContainer && (
    <div
      ref={popupRef}
      className="fixed pointer-events-auto"
      style={{
        left: `${position.left}px`,
        top: `${position.top}px`,
        zIndex: 10000,
      }}
      onMouseEnter={() => {
        handleMouseEnter();
      }}
      onMouseLeave={() => {
        handleMouseLeave();
      }}
    >
      {/* Arrow */}
      <div
        className={`absolute w-3 h-3 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rotate-45 ${position.placement === 'above'
            ? 'bottom-[-7px] border-t-0 border-l-0'
            : 'top-[-7px] border-b-0 border-r-0'
          }`}
        style={{
          left: `${position.arrow.left - 6}px`,
        }}
      />

      {/* Popup Card */}
      <div
        className={`bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl shadow-[0_8px_32px_rgba(0,0,0,0.3)] w-[480px] max-w-[90vw] flex flex-col overflow-hidden backdrop-blur-[10px] ${position.placement === 'above' ? 'animate-slideInUp' : 'animate-slideInDown'
          }`}
      >
        {/* Header */}
        <div className="px-5 py-4 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
          {source.document && (
            <div className="font-bold text-blue-500 dark:text-blue-400 mb-2 text-sm">
              {source.document}
            </div>
          )}
          <div className="text-[13px] font-semibold text-gray-600 dark:text-gray-400">
            Pages {source.page_range} • {(source.similarity * 100).toFixed(1)}% relevance
          </div>
        </div>

        {/* Content */}
        <div className="px-6 py-5 text-sm leading-[1.8] text-gray-900 dark:text-gray-100 overflow-y-auto max-h-[400px] [&::-webkit-scrollbar]:w-[10px] [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-track]:my-2 [&::-webkit-scrollbar-thumb]:bg-gray-300 [&::-webkit-scrollbar-thumb]:dark:bg-gray-600 [&::-webkit-scrollbar-thumb]:rounded-[5px] [&::-webkit-scrollbar-thumb]:border-2 [&::-webkit-scrollbar-thumb]:border-transparent [&::-webkit-scrollbar-thumb]:bg-clip-padding [&::-webkit-scrollbar-thumb:hover]:bg-gray-400 [&::-webkit-scrollbar-thumb:hover]:dark:bg-gray-500">
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown
              components={{
                h1: ({ node, ...props }) => <h1 className="text-lg font-bold mb-3 mt-4 first:mt-0 text-gray-900 dark:text-gray-100" {...props} />,
                h2: ({ node, ...props }) => <h2 className="text-base font-bold mb-2 mt-3 first:mt-0 text-gray-900 dark:text-gray-100" {...props} />,
                h3: ({ node, ...props }) => <h3 className="text-sm font-bold mb-2 mt-3 first:mt-0 text-gray-900 dark:text-gray-100" {...props} />,
                h4: ({ node, ...props }) => <h4 className="text-sm font-semibold mb-2 mt-2 first:mt-0 text-gray-800 dark:text-gray-200" {...props} />,
                p: ({ node, ...props }) => <p className="mb-3 last:mb-0 text-gray-700 dark:text-gray-300" {...props} />,
                ul: ({ node, ...props }) => <ul className="list-disc list-outside ml-5 mb-3 space-y-1 text-gray-700 dark:text-gray-300" {...props} />,
                ol: ({ node, ...props }) => <ol className="list-decimal list-outside ml-5 mb-3 space-y-1 text-gray-700 dark:text-gray-300" {...props} />,
                li: ({ node, ...props }) => <li className="pl-1" {...props} />,
                strong: ({ node, ...props }) => <strong className="font-semibold text-gray-900 dark:text-gray-100" {...props} />,
                em: ({ node, ...props }) => <em className="italic text-gray-800 dark:text-gray-200" {...props} />,
                code: ({ node, ...props }) => <code className="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs font-mono text-blue-600 dark:text-blue-400" {...props} />,
                blockquote: ({ node, ...props }) => <blockquote className="border-l-4 border-gray-300 dark:border-gray-600 pl-4 italic text-gray-600 dark:text-gray-400 my-3" {...props} />,
              }}
            >
              {source.content}
            </ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <>
      <sup
        ref={citationRef}
        className="relative inline-block mx-[2px] align-baseline cursor-pointer"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        <span className="inline-block text-blue-500 dark:text-blue-400 font-semibold text-[0.9em] px-1 py-0.5 rounded leading-none transition-all duration-200 hover:text-blue-600 dark:hover:text-blue-300 hover:bg-blue-500/10 dark:hover:bg-blue-400/10">
          [{number}]
        </span>
      </sup>
      {popupContent && createPortal(popupContent, portalContainer)}
    </>
  );
}