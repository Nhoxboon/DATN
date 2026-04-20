import { BookOpenText } from 'lucide-react'

export function LogoMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="inline-flex items-center gap-3">
      <span className="flex h-11 w-11 items-center justify-center rounded-[18px] bg-gradient-to-br from-primary to-primary-deep text-white shadow-paper">
        <BookOpenText className="h-5 w-5" />
      </span>
      <div className="space-y-0.5">
        <div className="font-display text-[0.7rem] uppercase tracking-[0.35em] text-muted">
          The Digital Atelier
        </div>
        {!compact && <div className="font-display text-xl font-semibold text-ink">Scholar Script</div>}
      </div>
    </div>
  )
}
