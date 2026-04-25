interface SourcesSkeletonProps {
  count?: number;
}

export function SourcesSkeleton({ count = 5 }: SourcesSkeletonProps) {
  return (
    <>
      {Array.from({ length: count }).map((_, index) => (
        <div
          key={index}
          className="px-3 py-3 rounded-lg bg-white dark:bg-gray-800 animate-pulse"
          style={{
            animationDelay: `${index * 100}ms`,
          }}
        >
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-gray-200 dark:bg-gray-700" />
            <div className="flex-1 space-y-2">
              <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-3/4" />
              <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-1/2" />
            </div>
          </div>
        </div>
      ))}
    </>
  );
}