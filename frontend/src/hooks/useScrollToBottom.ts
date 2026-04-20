import { useEffect, useRef } from 'react'

export function useScrollToBottom<T>(dependency: T) {
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const node = ref.current

    if (!node) {
      return
    }

    node.scrollTop = node.scrollHeight
  }, [dependency])

  return ref
}
