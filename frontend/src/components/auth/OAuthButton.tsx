import type { ButtonHTMLAttributes } from 'react'
import { Button } from '../shared/Button'

interface OAuthButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string
}

export function OAuthButton({ label, ...props }: OAuthButtonProps) {
  return (
    <Button
      variant="secondary"
      className="w-full rounded-(--radius-pill) bg-white text-ink shadow-[inset_0_0_0_1px_rgba(171,179,183,0.2)]"
      {...props}
    >
      <span className="text-base">G</span>
      {label}
    </Button>
  )
}
