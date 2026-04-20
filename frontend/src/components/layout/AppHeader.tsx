import type { Ref } from 'react'
import { Bell, Search, Settings } from 'lucide-react'
import { Button } from '../shared/Button'

interface AppHeaderProps {
  title: string
  subtitle: string
  actions?: 'dashboard' | 'editor'
  avatar: string
  onAvatarClick: () => void
  avatarButtonRef?: Ref<HTMLButtonElement>
}

export function AppHeader({
  title,
  subtitle,
  actions = 'dashboard',
  avatar,
  onAvatarClick,
  avatarButtonRef,
}: AppHeaderProps) {
  return (
    <header className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
      <div className="space-y-3">
        <div className="font-display text-xs uppercase tracking-[0.34em] text-muted">The Scholarly Curator</div>
        <div className="space-y-3">
          <h1 className="font-display text-4xl font-semibold leading-tight text-ink sm:text-5xl">{title}</h1>
          <p className="max-w-3xl text-base leading-8 text-muted">{subtitle}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 self-start">
        <button
          type="button"
          className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-white text-muted shadow-paper transition hover:text-ink"
          aria-label="Search"
        >
          <Search className="h-5 w-5" />
        </button>
        {actions === 'dashboard' && (
          <button
            type="button"
            className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-white text-muted shadow-paper transition hover:text-ink"
            aria-label="Settings"
          >
            <Settings className="h-5 w-5" />
          </button>
        )}
        {actions === 'editor' && (
          <button
            type="button"
            className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-white text-muted shadow-paper transition hover:text-ink"
            aria-label="Notifications"
          >
            <Bell className="h-5 w-5" />
          </button>
        )}
        <Button variant="secondary" className="h-12 rounded-full bg-white px-4 shadow-paper">
          <span className="text-xs uppercase tracking-[0.2em] text-muted">Studio</span>
        </Button>
        <button
          ref={avatarButtonRef}
          type="button"
          onClick={onAvatarClick}
          className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br from-primary to-primary-deep font-semibold text-white shadow-paper"
          aria-label="Open profile menu"
        >
          {avatar}
        </button>
      </div>
    </header>
  )
}
