import { Button } from '../shared/Button'

export function OAuthButton({ label }: { label: string }) {
  return (
    <Button
      variant="secondary"
      className="w-full rounded-(--radius-pill) bg-white text-ink shadow-[inset_0_0_0_1px_rgba(171,179,183,0.2)]"
    >
      <span className="text-base">G</span>
      {label}
    </Button>
  )
}
