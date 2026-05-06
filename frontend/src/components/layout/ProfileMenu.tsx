import type { RefObject } from 'react'
import { createPortal } from 'react-dom'
import { KeyRound, LogOut } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { UserProfile } from '../../types'
import { usePopupPosition } from '../../hooks/usePopupPosition'
import { usePortal } from '../../hooks/usePortal'

interface ProfileMenuProps {
  anchorRef: RefObject<HTMLElement | null>
  open: boolean
  profile: UserProfile | null
  onClose: () => void
  onSignOut: () => void
}

export function ProfileMenu({ anchorRef, open, profile, onClose, onSignOut }: ProfileMenuProps) {
  const portalTarget = usePortal()
  const position = usePopupPosition(anchorRef, open)

  if (!open || !portalTarget || !profile) {
    return null
  }

  return createPortal(
    <>
      <button
        type="button"
        aria-label="Close profile menu"
        className="fixed inset-0 z-40 bg-transparent"
        onClick={onClose}
      />
      <div
        className="glass-panel fixed z-50 w-56 rounded-3xl p-4 shadow-float"
        style={{ left: Math.max(position.left, 16), top: position.top }}
      >
        <div className="mb-4 flex min-w-0 items-center gap-3 rounded-[20px] bg-white/70 p-3">
          <div className="flex size-11 shrink-0 items-center justify-center rounded-full bg-linear-to-br from-primary to-primary-deep font-semibold text-white">
            {profile.avatarLabel}
          </div>
          <div className="min-w-0">
            <div className="truncate font-medium text-ink" title={profile.name}>
              {profile.name}
            </div>
            <div className="truncate text-sm text-muted" title={profile.role}>
              {profile.role}
            </div>
          </div>
        </div>
        <div className="space-y-1 text-sm">
          <Link
            to="/change-password"
            className="flex items-center gap-3 rounded-[18px] px-3 py-2.5 text-ink transition hover:bg-white/80"
            onClick={onClose}
          >
            <KeyRound className="h-4 w-4 text-primary" />
            Change password
          </Link>
          <button
            type="button"
            className="flex w-full items-center gap-3 rounded-[18px] px-3 py-2.5 text-left text-ink transition hover:bg-white/80"
            onClick={() => {
              onClose()
              onSignOut()
            }}
          >
            <LogOut className="h-4 w-4 text-primary" />
            Sign out
          </button>
        </div>
      </div>
    </>,
    portalTarget,
  )
}
