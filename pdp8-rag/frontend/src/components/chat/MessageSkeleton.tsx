export function MessageSkeleton() {
  return (
    <div className="flex justify-start animate-pulse">
      <div className="flex items-start gap-3 max-w-[95%]">
        <div className="flex-shrink-0 w-8 h-8 bg-gray-300 dark:bg-gray-700 rounded-full" />
        <div className="flex-1 space-y-2">
          <div className="bg-gray-200 dark:bg-gray-800 px-4 py-3 rounded-2xl rounded-tl-sm">
            <div className="space-y-2">
              <div className="h-4 bg-gray-300 dark:bg-gray-700 rounded w-3/4" />
              <div className="h-4 bg-gray-300 dark:bg-gray-700 rounded w-full" />
              <div className="h-4 bg-gray-300 dark:bg-gray-700 rounded w-5/6" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}