import { useState, useEffect } from 'react';
import { Bot } from 'lucide-react';

const STREAMING_STAGES = [
  { time: 0, message: "Analyzing documents..." },
  { time: 15, message: "Processing your query..." },
  { time: 30, message: "Searching through regulations..." },
  { time: 45, message: "Generating response..." },
  { time: 70, message: "Compiling final answer..." },
  { time: 100, message: "Almost done..." },
];


export function StreamingIndicator() {
  const [messageIndex, setMessageIndex] = useState(0);

  useEffect(() => {
    const start = Date.now();

    const interval = setInterval(() => {
      const elapsedSec = Math.floor((Date.now() - start) / 1000);
      const stage = STREAMING_STAGES
        .filter(s => s.time <= elapsedSec)
        .slice(-1)[0];

      if (stage) {
        setMessageIndex(STREAMING_STAGES.indexOf(stage));
      }
    }, 1000);

    return () => clearInterval(interval);
  }, []);


  return (
    <div className="flex justify-start animate-[fadeIn_0.3s_ease-out]">
      <div className="flex items-start gap-3 max-w-[95%]">
        <div className="flex-shrink-0 w-8 h-8 bg-gradient-to-br from-gray-700 to-gray-800 dark:from-gray-600 dark:to-gray-700 rounded-full flex items-center justify-center shadow-lg">
          <Bot className="w-4 h-4 text-white" />
        </div>
        <div className="flex-1">
          <div className="bg-gray-100 dark:bg-gray-800 px-4 py-3 rounded-2xl rounded-tl-sm shadow-sm">
            <div className="flex items-center gap-3">
              {/* Animated dots */}
              <div className="flex gap-1">
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"
                    style={{
                      animationDelay: `${i * 0.15}s`,
                      animationDuration: '1s',
                    }}
                  />
                ))}
              </div>

              {/* Dynamic message */}
              <span className="text-sm text-gray-600 dark:text-gray-400 animate-[fadeIn_0.5s_ease-out]">
                {STREAMING_STAGES[messageIndex]?.message}
              </span>
            </div>

            {/* Shimmer effect */}
            <div className="mt-3 space-y-2">
              {[1, 2].map((i) => (
                <div
                  key={i}
                  className="h-3 bg-gradient-to-r from-gray-200 via-gray-300 to-gray-200 dark:from-gray-700 dark:via-gray-600 dark:to-gray-700 rounded animate-shimmer bg-[length:200%_100%]"
                  style={{
                    width: i === 1 ? '90%' : '60%',
                  }}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}