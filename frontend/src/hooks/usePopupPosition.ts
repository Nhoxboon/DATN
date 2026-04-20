import { useEffect, useState } from 'react'
import type { RefObject } from 'react'

interface PopupPosition {
  left: number
  top: number
}

export function usePopupPosition(
  anchorRef: RefObject<HTMLElement | null>,
  open: boolean,
  options?: { offset?: number },
) {
  const [position, setPosition] = useState<PopupPosition>({ left: 0, top: 0 })

  useEffect(() => {
    const anchor = anchorRef.current

    if (!anchor || !open) {
      return
    }

    const updatePosition = () => {
      const rect = anchor.getBoundingClientRect()
      const offset = options?.offset ?? 12

      setPosition({
        left: rect.right - 224,
        top: rect.bottom + offset,
      })
    }

    updatePosition()
    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', updatePosition, true)

    return () => {
      window.removeEventListener('resize', updatePosition)
      window.removeEventListener('scroll', updatePosition, true)
    }
  }, [anchorRef, open, options?.offset])

  return position
}
