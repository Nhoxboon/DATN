import { useEffect, useRef, RefObject } from 'react';

export interface UseScrollToBottomOptions {
  dependencies: any[];
  behavior?: ScrollBehavior;
  enabled?: boolean;
}

export function useScrollToBottom<T extends HTMLElement = HTMLDivElement>(
  options: UseScrollToBottomOptions
): RefObject<T> {
  const ref = useRef<T>(null);
  const { dependencies, behavior = 'smooth', enabled = true } = options;

  useEffect(() => {
    if (!enabled || !ref.current) return;

    const scrollToBottom = () => {
      ref.current?.scrollTo({
        top: ref.current.scrollHeight,
        behavior,
      });
    };

    // Small delay to ensure DOM has updated
    const timeoutId = setTimeout(scrollToBottom, 100);

    return () => clearTimeout(timeoutId);
  }, dependencies);

  return ref;
}