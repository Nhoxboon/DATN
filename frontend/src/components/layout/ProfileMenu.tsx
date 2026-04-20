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
}

export function ProfileMenu({ anchorRef, open, profile, onClose }: ProfileMenuProps) {
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
        <div className="mb-4 flex items-center gap-3 rounded-[20px] bg-white/70 p-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-linear-to-br from-primary to-primary-deep font-semibold text-white">
            {profile.avatarLabel}
          </div>
          <div>
            <div className="font-medium text-ink">{profile.name}</div>
            <div className="text-sm text-muted">{profile.role}</div>
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
          <Link
            to="/login"
            className="flex items-center gap-3 rounded-[18px] px-3 py-2.5 text-ink transition hover:bg-white/80"
            onClick={onClose}
          >
            <LogOut className="h-4 w-4 text-primary" />
            Sign out
          </Link>
        </div>
      </div>
    </>,
    portalTarget,
  )
}
