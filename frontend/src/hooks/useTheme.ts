import { useEffect } from 'react'

export function useTheme() {
  useEffect(() => {
    document.documentElement.dataset.theme = 'light'
  }, [])
}
