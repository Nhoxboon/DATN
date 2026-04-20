import { useDeferredValue } from 'react'

export function useTypewriter(text: string, speed = 14) {
  const deferredText = useDeferredValue(text)

  return speed > 0 ? deferredText : text
}
