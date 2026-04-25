import { useState, useEffect, useRef } from 'react';

export interface UseTypewriterOptions {
  text: string;
  speed?: number; // milliseconds per character
  delay?: number; // initial delay before starting
  onComplete?: () => void;
}

export interface UseTypewriterReturn {
  displayedText: string;
  isTyping: boolean;
}

export function useTypewriter({
  text,
  speed = 1,
  delay = 0,
  onComplete,
}: UseTypewriterOptions): UseTypewriterReturn {
  const [displayedText, setDisplayedText] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const indexRef = useRef(0);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    // Reset when text changes
    setDisplayedText('');
    indexRef.current = 0;
    setIsTyping(true);

    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    if (!text) {
      setIsTyping(false);
      return;
    }

    const startTyping = () => {
      const type = () => {
        if (indexRef.current < text.length) {
          setDisplayedText(text.slice(0, indexRef.current + 1));
          indexRef.current++;
          timeoutRef.current = setTimeout(type, speed);
        } else {
          setIsTyping(false);
          onComplete?.();
        }
      };

      timeoutRef.current = setTimeout(type, delay);
    };

    startTyping();

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [text, speed, delay, onComplete]);

  return { displayedText, isTyping };
}